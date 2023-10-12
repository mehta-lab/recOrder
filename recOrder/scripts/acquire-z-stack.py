from time import sleep
from pycromanager import Core

NUM_Z_STEPS = 10
Z_INTERVAL_UM = 2
Z_STEP_INTERVAL_SECONDS = 1
NUM_TIME_POINTS = 5
TIME_INTERVAL_SECONDS = 1

mmc = Core(convert_camel_case=False)

for t_step in range(NUM_TIME_POINTS):
    print(f"Time = {t_step}")
    for z_step in range(NUM_Z_STEPS):
        mmc.setPosition(Z_INTERVAL_UM * z_step)
        print(f"Z position = {mmc.getPosition()}")
        sleep(Z_STEP_INTERVAL_SECONDS)
        # WRITE T = t_step, Z = z_step HERE

mmc._close()
