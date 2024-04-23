#!/bin/bash

PIDS=($(ps aux | grep watt_pilot_IOC.py |awk '{print $2}'))
CMDS=($(ps aux | grep watt_pilot_IOC.py |awk '{print $11}'))

for ((i=0;i<${#PIDS[*]};i++))
do
  # echo ${i}
  # echo ${PIDS[$i]}

   if [ ${CMDS[$i]} == "python" ]; then
     echo ${CMDS[$i]} ${PIDS[$i]}    
     kill -9 ${PIDS[$i]}
     echo "Kill ${PIDS[$i]}"
   else
    
     echo "skip ${CMDS[$i]}"     

   fi

done

