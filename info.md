Entity Controller turns entities on when a sensor triggers and off again after a delay, using a finite state machine that does not interfere with manual control or other automations. Typical use: motion-activated lights.

This edition is a regular integration managed entirely from **Settings → Devices & services → Integrations → Entity Controller**: add, configure, rename, disable and delete controllers there, and use each controller's device for its Activate / Clear block / Enable block buttons and Stay mode switch. Existing `entity_controller:` YAML is imported once. It fixes lights turning off while motion/presence sensors still report presence when several duration sensors are used, adds hold sensors for presence (mmWave) sensors, and includes many other fixes.

Remove the original Entity Controller before installing this version (same folder). See the README for all settings.
