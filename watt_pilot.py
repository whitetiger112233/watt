import asyncio
import time
import serial

class watt_pilot:
    def __init__(self, serial_port):
        config = {
            'serial_port': serial_port,
            'baudrate': 38400,
            'timeout': 2
            }
        self.ser = serial.Serial()
        self.ser.baudrate = config['baudrate']
        self.ser.port = config['serial_port']
        self.ser.timeout = config['timeout']
        self.ser.open()
        self.last_command_sent = time.time()
        self.update_setting()
        
    def update_setting(self):
        self.motor_all_setting = self.get_all_settings()
        self.motor_setting = self.get_settings()
        
    async def send_command(self, command, clear_echo=True, debug=True):
        self.ser.flushInput()
        if time.time() - self.last_command_sent < .05:
            await asyncio.sleep(0.05)
            
        if type(command) is bytes:
            command = command.decode()
        command = command.strip()
        self.ser.write(command.encode() + b'\r\n')
        self.last_command_sent = time.time()
        
        if clear_echo:
            echo = self.readline().strip()
            while echo != command:
                if debug:
                    print(echo)
                echo = self.readline().strip()
    
    def readline(self):
        return self.ser.readline().decode().strip()
    def close(self):
        self.ser.close()
    def __del__(self):
        self.close()
    async def get_all_settings(self):
        motor_settings_read_template = {
            'names': [
                'operating_mode', #1
                'current_motor_run_state', #2
                'acceleration', #3
                'deceleration', #4
                'speed', #5
                'motion_current', #6
                'idle_current', #7
                'motion_current_in_step_dir_mode', #8
                'micro_stepping_resolution', #9
                'motor_enabled', #10
                'reserved', #11
                'reset_position_on_zero_position', #12
                'report_when_hitting_zero_position', #13
                'reserved', #14
                'reserved', #15
                'reserved', #16
                'motor_direction_in_step_dir_mode', #17
                'motor_enable_in_step_dir_mode', #18
                'reserved', #19
                'switch_SW_F', #20
                'switch_SW_E', #21
                'reserved', #22
                'reserved', #23
                'reserved', #24        
            ],
            'types': [
                bool, int, int, int, int,
                int, int, int, int, bool, 
                None, bool, bool, None, None, 
                None, bool, bool, None, bool,
                bool, None, None, None
            ],
        }

        await self.send_command('pc')
        msg = self.readline().rstrip(';')
        result = {n: t(v) if t is not None else None \
                    for n, t, v in zip(
                        motor_settings_read_template['names'],
                        motor_settings_read_template['types'], 
                        msg.split(';')
                    )}
        if 'micro_stepping_resolution' in result.keys() and result['micro_stepping_resolution'] == 6:
            result['micro_stepping_resolution'] = 16
        if 'micro_stepping_resolution' in result.keys() and 'speed' in result.keys():
            result.update(
                {
                    'angular_rotation_speed': 14400000/78/result['micro_stepping_resolution']/(65535-result['speed']),
                    'steps_per_revolution': 15600 * result['micro_stepping_resolution']
                }
            )
        return result

    async def get_settings(self):
        keywords_trans = {
            'a': 'acceleration',
            'd': 'deceleration',
            'r': 'micro_stepping_resolution',
            's': 'speed',
            'wm': 'motion_current',
            'ws': 'idle_current',
            'wt': 'motion_current_in_step_dir_mode',
            'en': 'motor_enabled',
            'zr': 'report_when_hitting_zero_position',
            'zs': 'reset_position_on_zero_position'
        }
        await self.send_command('p', clear_echo=False)
        msg = self.readline()
        if msg.startswith('pUSB:'):
            result = {'operating_mode': bool(msg.split(' ')[1])}
            for param in msg.split(' ')[2:]:
                if '=' in param:
                    result[keywords_trans[param.split('=')[0]]] = int(param.split('=')[1])
                elif ':' in param:
                    result[keywords_trans[param.split(':')[0]]] = bool(param.split(':')[1])
            if 'micro_stepping_resolution' in result.keys() and result['micro_stepping_resolution'] == 6:
                result['micro_stepping_resolution'] = 16
            if 'micro_stepping_resolution' in result.keys() and 'speed' in result.keys():
                result.update(
                    {
                        'angular_rotation_speed': 14400000/78/result['micro_stepping_resolution']/(65535-result['speed']),
                        'steps_per_revolution': 15600 * result['micro_stepping_resolution']
                    }
                )
            return result
        else:
            print('Watt Pilot is not attached or turned on.')

    async def get_state(self):
        await self.send_command('o')
        msg = self.readline()
        if len(msg) > 0:
            msg = msg.split(';')
            result = {'run_state': int(msg[0]), 'position': int(msg[1])}
            result['state_description'] = {
                0: 'stopped',
                1: 'accelerating',
                2: 'decelerating',
                3: 'moving'
            }[result['run_state']]
            return result
        else:
            print('Failed to get a current state.')

    def get_device_name(self):
        self.send_command('n')
        msg = self.readline()
        return msg.strip()

    def save_settings(self):
        self.send_command('ss')

    def reset_controller(self):
        self.send_command('j')

    def set_position_reporting(self, enable=True):
        self.send_command('zr {}'.format(int(enable)))

    def set_microstep_resolution(self, new_res):
        if type(new_res) is not int:
            new_res = int(new_res)
        if new_res in [1, 2, 4, 8, 16, 6]:
            if new_res == 16:
                new_res = 6
            self.send_command('r {}'.format(new_res))
        else:
            print("Wrong value for microstep resolution.")
            
    def set_acceleration(self, new_value):
        if type(new_value) is not int:
            new_value = int(new_value)
        if new_value > 0 and new_value<255:
            self.send_command('a {}'.format(new_value))
            if new_value == 0:
                print("Acceleration is turned off.")
        else:
            print("Wrong value for acceleration.")
    
    def set_deceleration(self, new_value):
        if type(new_value) is not int:
            new_value = int(new_value)
        if new_value > 0 and new_value<255:
            self.send_command('d {}'.format(new_value))
            if new_value == 0:
                print("Deceleration is turned off.")
        else:
            print("Wrong value for deceleration.")
            
    async def move_by(self, steps, wait=False):
        if type(steps) != int:
            steps = int(steps)
        #steps = steps % self.motor_setting['steps_per_revolution']
        await self.send_command('m {}'.format(steps))
        
        if wait:
            new_state = await self.get_state()
            while new_state is None or new_state['run_state'] != 0:
                await asyncio.sleep(0.1)
                new_state = await self.get_state()

    async def move_to(self, position, wait=False, debug=False):
        if type(position) != int:
            position = int(position)
        #position = position % self.motor_setting['steps_per_revolution']
        command = 'g {}'.format(position)
        current_state = await self.get_state()
        if debug:
            print(command)
        if current_state['position'] != position:
            await self.send_command(command)

            if wait:
                new_state = await self.get_state()
                while new_state is None or new_state['run_state'] != 0:
                    await asyncio.sleep(0.1)
                    new_state = await self.get_state()
    
    async def home(self, wait = False):
        await self.send_command('zp')
        
        if wait:
            new_state = await self.get_state()
            while new_state is None or new_state['run_state'] != 0:
                await asyncio.sleep(0.1)
                new_state = await self.get_state()
    
    def stop(self):
        self.send_command('st')
    
    def set_position(self, new_position_value):
        if type(new_position_value) != int:
            new_position_value = int(new_position_value)
        
        if new_position_value == 0:
            self.send_command('h')
        else:
            self.send_command('i {}'.format(new_position_value))