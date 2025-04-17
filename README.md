# final-project-code
Steps for installing:

1. Clone repo

2. Confirm I2C is enabled: `sudo raspi-config` --> Interfacing Options --> I2C --> Enable --> `sudo reboot`

3. If VL53L0X is connected, (assuming i2c-tools is installed) check using `i2cdetect -y 1`

4. Set up virtual environment `python3 -m venv .venv` and activate `source .venv/bin/activate`

5. Install required packages: `pip3 install -r requirements.txt`

6. Run: `python3 <filename>`