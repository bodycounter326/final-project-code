# final-project-code
Steps for intalling:

1. Clone repo
2. Confirm I2C is enabled: <sudo raspi-config> --> Interfacing Options --> I2C --> Enable --> <sudo reboot>
3. If VL53L0X is connected, (assuming i2c-tools is installed) checki using <i2cdetect -y 1>
3. Set up virtual environment using <python3 -m venv proj-env>
3. Install required packages:  
