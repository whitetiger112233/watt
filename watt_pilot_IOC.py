#!/usr/bin/env python3

from caproto import ChannelType
from caproto.server import pvproperty, PVGroup, ioc_arg_parser, run
from watt_pilot import watt_pilot
import json
import time

from math import pi, cos, sin, sqrt
rad_to_step = lambda rad: int(31200*rad/pi) 
step_to_rad = lambda step: step/31200*pi  

def rad_to_power(rad):  
    amp = config['800nm']['amp']
    x0 = config['800nm']['p0']
    extingt_coeff = config['800nm']['extingt']
    polar_ratio = config['800nm']['polar_ratio']

    rad_from_min = (rad-x0)
    values_p = amp*(1-polar_ratio)*sin(rad_from_min*4)
    values_o = amp*polar_ratio*cos(rad_from_min*4)

    return values_p**2 + values_o**2 + amp/extingt_coeff

def rad_to_power_only_P(rad):
    amp = sqrt(config['800nm']['amp'])
    x0 = config['800nm']['p0']
    extingt_coeff = config['800nm']['extingt']
    polar_ratio = config['800nm']['polar_ratio']

    values_p = amp*(1-polar_ratio)*sin((rad-x0)*4)
    values_o = amp*polar_ratio*cos((rad-x0)*4)

    return values_p**2

def polyval(p, x):
    value = 0
    for i, p_sub in enumerate(p[::-1]):
        value += p_sub * x**i
    return value
        
def idx_closest(l, lookup_value):
    a = [abs(el - lookup_value) for el in l]
    return a.index(min(a))

with open('config.json', 'r') as f:
    config = json.load(f)
config

power_table={}

def update_power_table(cwl = 800, loss_factor = 1):
    global power_table

    if cwl == 800:
        lf_800 = loss_factor
    elif cwl == 400:
        lf_800 = polyval(config['400nm']['loss_factor_conversion_factor'], loss_factor)
        
    power_table={
        'step': [],
        'radian': [],
        800: {
            'power': [],
            'power_percentile': [],
            'max_power': rad_to_power(config['800nm']['p0']+pi/8) * lf_800
        },
        400: {
            'power': [],
            'power_percentile': [],
            'max_power': polyval(
                config['400nm']['conversion_factor'], 
                rad_to_power_only_P(config['800nm']['p0']+pi/8) * lf_800
            )
        }
    }
    print(power_table)
    
    for p in range(rad_to_step(config['800nm']['p0']), rad_to_step(config['800nm']['p0'] + pi/8) + 1):
        power_table['step'].append(p)
        rad = step_to_rad(p)
        power_table['radian'].append(rad)

        power = rad_to_power(rad) * lf_800
        power_table[800]['power'].append(power)
        power_table[800]['power_percentile'].append(power*100/power_table[800]['max_power'])

        power_800_p = rad_to_power_only_P(rad) * lf_800
        power = polyval(
                    config['400nm']['conversion_factor'], 
                    power_800_p
                )
        power_table[400]['power'].append(power)
        power_table[400]['power_percentile'].append(power*100/power_table[400]['max_power'])

update_power_table()

class watt_pilot_ioc(PVGroup):
    controller = watt_pilot(config['serial']['port'])
    
    is_moving = pvproperty(value=False, dtype=bool)
    @is_moving.startup
    async def is_moving(self, instance, async_lib):
        print("Start homing...")
        await self.controller.home(wait=True)
        print("Home is found. Go to a position for minimum power.")
        await self.controller.move_to(
            power_table['step'][idx_closest(power_table[800]['power'], 0)],
            wait = True
        )
        print("Minimum power, Now.")
    
    
    position = pvproperty(value=0, dtype=int)
    position_RBV = pvproperty(value=0, dtype=int)
    
    @position.putter
    async def position(self, instance, value):
        moving_status = await self.is_moving.read(ChannelType.INT)
        if moving_status[1][0] == True:
            print('Maybe motor is still moving. current moving status is {}'.format(self.is_moving.value))
            return self.position_RBV.value
        else:
            print("Moving motor...")
            await self.is_moving.write(value = True)
            await self.controller.move_to(value, wait=True)
            await self.is_moving.write(value = False)
            print("Moving finished. Current moving status is {}".format(self.is_moving.value))

            new_state = await self.controller.get_state()
            while new_state is None:
                new_state = await self.controller.get_state()
        
            await self.position_RBV.write(value = new_state['position'])
            return self.position_RBV.value
    
    cwl_RBV = pvproperty(value=config['IOC']['CWL'], dtype=int)
    cwl = pvproperty(value=config['IOC']['CWL'], dtype=int)
    @cwl.putter
    async def cwl(self, instance, value):
        if value in [k for k in power_table.keys() if type(k) == int]:
            update_power_table(value, self.loss_factor_RBV.value)
            await self.percent.write(self.percent_RBV.value)
            await self.cwl_RBV.write(value = value)
        else:
            raise ValueError('Invalid value!')
        return self.cwl_RBV.value
    
    hi_limit_RBV = pvproperty(value=100.)    
    hi_limit = pvproperty(value=100.)
    @hi_limit.putter
    async def hi_limit(self, instnace, value):
        await self.hi_limit_RBV.write(value = max(0, min(100, value)))
        return self.hi_limit_RBV.value

    lo_limit_RBV = pvproperty(value=0.)
    lo_limit = pvproperty(value=0.)
    @lo_limit.putter
    async def lo_limit(self, instnace, value):
        await self.lo_limit_RBV.write(value = max(0, min(100, value)))
        return self.lo_limit_RBV.value
        
    loss_factor_RBV = pvproperty(value=1.)
    loss_factor = pvproperty(value=1.)
    @loss_factor.putter
    async def loss_factor(self, instance, value):
        update_power_table(self.cwl_RBV.value, value)
        await self.loss_factor_RBV.write(value = max(0, min(1, value)))
        await self.percent.write(self.percent_RBV.value)
        return self.loss_factor_RBV.value
    
    percent_RBV = pvproperty(value=min(power_table[config['IOC']['CWL']]['power_percentile']))
    percent = pvproperty(value=min(power_table[config['IOC']['CWL']]['power_percentile']))
    @percent.putter
    async def percent(self, instance, value):
        cwl = self.cwl_RBV.value
        power_percentile_list = power_table[cwl]['power_percentile']
        target_value = max(self.lo_limit_RBV.value, min(self.hi_limit_RBV.value, value))
        idx = idx_closest(power_percentile_list, target_value)
        if self.position.value != power_table['step'][idx]:
            await self.position.write(value = power_table['step'][idx])
        if self.percent_RBV.value != power_percentile_list[idx]:
            await self.percent_RBV.write(value = power_percentile_list[idx])
        await self.mJ_RBV.write(value = power_table[cwl]['power'][idx]*1000)
        await self.mJ.write(value = self.mJ_RBV.value)
        return self.percent_RBV.value
    
    mJ_RBV = pvproperty(value = min(power_table[config['IOC']['CWL']]['power'])*1000)
    mJ = pvproperty(value = min(power_table[config['IOC']['CWL']]['power'])*1000)
    @mJ.putter
    async def mJ(self, instance, value):
        cwl = self.cwl_RBV.value
        if value != self.mJ_RBV.value:
            power_list = [p*1000 for p in power_table[cwl]['power']]
            idx = idx_closest(power_list, value)
            await self.mJ_RBV.write(value = power_list[idx]*1000)
            await self.percent.write(value = power_table[cwl]['power_percentile'][idx])
        return self.mJ_RBV.value

if __name__ == '__main__':
    ioc_options, run_options = ioc_arg_parser(
        default_prefix=config['IOC']['pv_prefix'],
        desc=config['IOC']['description'])
    print("PV prefix: ", config['IOC']['pv_prefix'])
    ioc = watt_pilot_ioc(**ioc_options)
    #udp_sock = caproto.bcast_socket()
    run(ioc.pvdb, **run_options)
