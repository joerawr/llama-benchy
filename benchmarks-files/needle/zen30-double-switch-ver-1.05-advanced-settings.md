---
title: "ZEN30 Double Switch VER. 1.05 Advanced Settings"
source: "https://www.support.getzooz.com/kb/article/468-zen30-double-switch-advanced-settings/"
author:
  - "[[text]]"
published:
created: 2026-06-18
description:
tags:
  - "clippings"
---
## Here is a full list of advanced settings (parameters) for ZEN30 Double Switch

Some parameters were added in later firmware updates so please make sure you're on the latest firmware to have all of the settings below available (not all are available on 500 series Hardware Versions 1 & 2. [You can view the change log for the ZEN30 here](https://www.support.getzooz.com/kb/article/393-zen30-double-switch-change-log/)[.](https://www.support.getzooz.com/kb/article/849-zen72-700-series-dimmer-change-log/)

### Dimmer LED Indicator

**Parameter 1:** Choose if you want the LED indicator to turn on when the **dimmer** (light) is on or off, or if you want it to remain on or off at all times. This setting is for the top status indicator only.

**Values:** 0 – LED on when dimmer off; 1 – LED on when dimmer on; 2 – LED always off; 3 – LED always on Default: 0.

**NOTE:** tap the upper paddle 6 times quickly to change this mode.

**Size:** 1 byte dec

### Relay LED Indicator

**Parameter 2:** Choose if you want the LED indicator to turn on when the **relay** is on or off, or if you want it to remain on or off at all times.

**Values:** 0 – LED on when relay off; 1 – LED on when relay on; 2 – LED always off; 3 – LED always on Default: 0.

**NOTE:** tap the relay button 6 times quickly to change this mode.

**Size:** 1 byte dec

### Dimmer LED Indicator Color

**Parameter 3:** Choose the **color** of the LED indicators of the **dimmer**.

**Values:** 0 – white; 1 – blue; 2 – green; 3 – red. Default: 0.

**Size:** 1 byte dec

### Relay LED Indicator Color

**Parameter 4:** Choose the **color** of the LED indicator of the **relay**.

**Values:** 0 – white; 1 – blue; 2 – green; 3 – red. Default: 0.

**Size:** 1 byte dec

### Dimmer LED Indicator Brightness

**Parameter 5:** Choose the LED indicators’ **brightness** level for the **dimmer**.

**Values:** 0 – bright (100%); 1 – medium (60%); 2 – low (30%). Default: 1.

**Size:** 1 byte dec

### Relay LED Indicator Brightness

**Parameter 6:** Choose the LED indicator's **brightness** level for the **relay**.

**Values:** 0 – bright (100%); 1 – medium (60%); 2 – low (30%). Default: 1.

**Size:** 1 byte dec

### Scene LED Indicator

**Parameter 7:** Choose if you want the LED indicators next to the dimmer to light up when a scene is selected.

You’ll see 1 to 5 LEDs light up for 1 – 5 tap triggers and 6 LEDs light up for the press-and-hold trigger of any paddle / button used.

**Values:** 0 – LEDs enabled for scene triggers; 1 – LEDs disabled for scene triggers. Default: 1.

**Size:** 1 byte dec

### Dimmer Auto Turn-Off Timer

**Parameter 8:** Auto-off timer will automatically turn the dimmer off after x minutes once it has been turned on**.**

Use this parameter to enable or disable the auto turn-off timer function for the dimmer (the time after which you want the dimmer to automatically turn off once it has been turned on).

**Values:** 0 – timer disabled; 1 – 65535 (minutes). Default: 0.

**Size:** 4 byte dec

### Dimmer Auto Turn-On Timer

**Parameter 9:** Use this parameter to enable or disable the auto turn-on timer function for the dimmer (the time after which you want the dimmer to automatically turn on once it has been turned off).

**Values:** 0 – timer disabled; 1 – 65535 (minutes). Default: 0.

**Size:** 4 byte dec

### Relay Auto Turn-Off Timer

**Parameter 10:** Auto-on timer will automatically turn the dimmer on after x minutes once it has been turned off.

Use this parameter to enable or disable the auto turn-off timer function for the relay (the time after which you want the relay to automatically turn off once it has been turned on).

**Values:** 0 – timer disabled; 1 – 65535 (minutes). Default: 0.

**Size:** 4 byte dec

### Relay Auto Turn-On Timer

**Parameter 11:** Auto-on timer will automatically turn the relay on after x minutes once it has been turned off.

Use this parameter to enable or disable the auto turn-on timer function for the relay (the time after which you want the dimmer to automatically turn on once it has been turned off).

**Values:** 0 – timer disabled; 1 – 65535 (minutes). Default: 0.

**Size:** 4 byte dec

### On Off Status After Power Failure

**Parameter 12:** Set the on off status for the dimmer and relay after power failure.

**Values:** 1 – dimmer forced to off, relay forced to on; 2 – dimmer forced to on, relay forced to off; 3 – remembers and restores on/off status for dimmer and relay after power failure; 4 – remembers and restores on/off status for dimmer, relay forced to on; 5 – remembers and restores on/off status for dimmer, relay forced to off; 6 – dimmer forced to on, remembers and restores on/off status for relay; 7 – dimmer forced to off, remembers and restores on/off status for relay; 8 – dimmer and relay forced to on. Default: 3.

**Size:** 1 byte dec

### Physical Ramp Rate ON

**Parameter 13:** Adjust the ramp rate ON for your dimmer when the top paddle is pressed for a smooth fade-in effect (in seconds).

Values correspond to the number of seconds it takes for the dimmer to reach full brightness when operated manually.

**Values:** 0 – instant on; 1 – 99 (seconds). Default: 0.

**Size:** 1 byte dec

***NOTE:*** On all other previous firmware versions, this setting was used for all ramp rate control (to adjust behavior for on/off physical and Z-Wave ramp rate). The default value for this parameter used to be 1.

### Minimum Brightness

**Parameter 14:** Set the minimum brightness level (in %) for the dimmer. You won’t be able to dim the light below the set value.

**Values:** 1 – 99 (%). Default: 1.

**Size:** 1 byte dec

### Maximum Brightness

**Parameter 15:** Set the maximum brightness level (in %) for the dimmer. You won’t be able to add brightness to the light beyond the set value.

**Values:** 1 – 99 (%). Default: 99.

**Size:** 1 byte dec

### Multilevel Dimming Reports

**Parameter 16**: Choose how you'd like the dimmer to report when paddles are tapped and held and physical / Z-Wave control is enabled or disabled.

See parameter 20 (smart bulb mode) for details.

**Values**: 0 – Reports each brightness level if physical and Z-Wave control disabled (reports final level if physical and Z-Wave control enabled); 1 – Always reports final brightness level only (Z-Wave multilevel reports, physical basic reports). Default: 0.

**Size**: 1 byte dec

### Dimmer Double Tap Up

**Parameter 17:** Choose what you'd like the dimmer to do when you double-tap the upper paddle.

This is a different setting than scene control so remember to program only one of the settings to avoid logical conflict.

**Values:** 0 – on to full brightness; 1 – on to the custom brightness (from param 23); 2 – on to max brightness (from param 15); 3 – double tap disabled. Default: 0.

**Size:** 1 byte dec

### Dimmer Single Tap Up

**Parameter 18:** Choose what you'd like the dimmer to do when you tap the upper paddle once. This is a different setting than scene control so remember to program only one of the settings to avoid logical conflict.

**Values:** 0 – on to the last brightness level; 1 – on to the custom brightness (from param 23); 2 – on to max brightness (from param 15); 3 – on to full brightness. Default: 0.

**Size:** 1 byte dec

### Dimmer Load Control (Smart Bulb Mode)

**Parameter 19:** Enable or disable physical and Z-Wave on/off and dimming control for the dimmer. Disable both physical paddle and Z-Wave control for smart bulbs (use central scene triggers). Scene control and other functionality will still be available from paddles.

**Values:** 0 – Disable paddle; 1 – Enable paddle and Z-Wave; 2 – Disable paddle and Z-Wave Default: 1.

**Size:** 1 byte dec

### Relay Load Control (Smart Bulb Mode)

**Parameter 20:** Enable or disable physical and Z-Wave on/off control for the relay. Disable both physical paddle and Z-Wave control for smart bulbs (use central scene triggers). Scene control and other functionality will still be available from paddles.

**Values:** 0 – Disable button; 1 – Enable button and Z-Wave; 2 – Disable button and Z-Wave. Default: 1.

**Size:** 1 byte dec

### Dimming Speed

**Parameter 21:** Set the time it takes to get from 0% to 100% brightness when pressing and holding the paddle (physical dimming).

The number entered as value corresponds to the number of seconds.

**Values:** 1 – 99 (seconds). Default: 4.

**Size:** 1 byte dec

### Match Z-Wave and Physical Ramp Rates

**Parameter 22:** Choose if you would like to match the **Z-Wave on/off ramp rate** with the manual ramp rate or set it separately in your hub.

**Values:** 0 – Z-Wave on/off ramp rate matches the manual ramp rate set in Parameter 13 (default). 1 – Z-Wave on/off ramp rate is set separately through its command class in the hub.

**Size:** 1 byte dec

(parameter removed in firmware 1.05)

### Dimmer Physical Custom Brightness On

**Parameter 23:** Set the custom brightness level (or leave the last brightness level) for single tap and double tap on the dimmer (see parameters 17 and 18).

**Values:** 0 – last brightness level (default); 1 – 99 (%). Default: 0.

**Size:** 1 byte dec

### Dimmer Disabled Load Behavior

**Parameter 24:** Set reporting behavior for disabled physical control of the load connected to the **dimmer** (smart bulb mode).

**Values:** 0 – Reports status / changes LED; 1 – Doesn't report status / change LED. Default: 0.

**Size**: 1 byte dec

### Relay Disabled Load Behavior

**Parameter 25:** Set reporting behavior for disabled physical control of the load connected to the relay (smart bulb mode).

**Values:** 0 – Reports status / changes LED; 1 – Doesn't report status / change LED. Default: 0.

**Size**: 1 byte dec

### Dimmer Night Light

**Parameter 26:** Set the brightness level the **dimmer** will turn on to when off and when the lower paddle is held DOWN for 2.5-3 seconds.

**Values:** 0 – feature disabled; 1 – 99 (%). Default: 20.

**Size:** 1 byte dec

### Dimmer Paddle Orientation

**Parameter 27:** Choose if you want the upper paddle to turn the light on or turn the light off when tapped.

**Values:** 0 – Up for on, down for off; 1 – Up for off, down for on; 2 – Up or down for on/off. Default: 0.

**Size:** 1 byte dec

### Dimmer Scene Control

**Parameter 28:** Enable or disable scene control functionality for quick multi tap triggers on the **dimmer**.

**Values:** 0 – scene control disabled. 1 – scene control enabled. Default: 1.

**Size:** 1 byte dec

### Relay Scene Control

**Parameter 29:** Enable or disable scene control functionality for quick double tap triggers on the **relay button**.

**Values:** 0 – scene control disabled. 1 – scene control enabled. Default: 1.

**Size:** 1 byte dec

### Disable Dimmer Paddle Programming

**Parameter 30:** Enable or disable programming functionality on the dimmer paddles.

If this setting is disabled, then inclusion, exclusion, smart bulb mode no longer work when dimmer paddles are activated (factory reset and scene control will still work) - that means you can now use triple-tap triggers on the dimmer for scenes and remote control of other devices.

**Values:** 0 – programming enabled. 1 – programming disabled. Default: 0.

**Size:** 1 byte dec

### Physical Ramp Rate OFF

**Parameter 31:** Adjust the ramp rate OFF for your dimmer when the bottom paddle is pressed for a smooth fade-out effect (in seconds).

**Values:** 0 – instant off; 1 – 99 (seconds). Default: 2.

**Size:** 1 byte dec

### Z-Wave Ramp Rate ON

**Parameter 32:** Adjust the ramp rate ON for your dimmer when controlled with Z-Wave for a smooth fade-in effect (in seconds). Values correspond to the number of seconds it takes for the dimmer to reach full brightness when controlled with Z-Wave commands. Use value 255 to match the physical settings in parameter 9.

**Values:** 0 – instant on; 1 – 99 (seconds); 255 – match physical. Default: 255.

**Size:** 1 byte dec

### Z-Wave Ramp Rate OFF

**Parameter 33:** Adjust the ramp rate OFF for your dimmer when controlled with Z-Wave for a smooth fade-out effect (in seconds). Values correspond to the number of seconds it takes for the dimmer to completely turn off when controlled with Z-Wave commands. Use value 255 to match the physical settings in parameter 27.

**Values:** 0 – instant off; 1 – 99 (seconds); 255 – match physical. Default: 255.

**Size:** 1 byte dec

### Disable LED Indicator Flash On Setting Change

**Parameter 34**: Choose if the LED should flash whenever a parameter is adjusted on the device to confirm the change or disable this feature. Disable this feature if you're using the LED indicators in automations.

**Values**: 0 – LED indicator flashes to confirm a setting change; 1 - LED indicator doesn't flash if a setting is changed. Default: 0.

**Size**: 1 byte dec

### Association Reports

**Parameter 35**: Choose physical and Z-Wave triggers for the device to send a status change report to the associated devices. See manual for details.

**Values**: 0 – none; 1 – physical tap on ZEN30 only; 2 – timer only; 3 – physical tap on ZEN30 or timer; 4 – Z-Wave command from hub; 5 – physical tap on ZEN30 or Z-Wave command from hub; 6 – Z-Wave command from hub or timer; 7 – physical tap on ZEN30, Z-Wave command from hub, or timer. Default: 7.

**Size**: 1 byte dec

### On Off Switch Mode

**Parameter 36**: Convert the dimmer to an on off switch. When enabled, the dimmer will behave as a switch without the ability to dim.

All ramp rates will be set to instant ON/OFF and the brightness level will be locked at 99%.

**Values**: 0 – disabled; 1 – enabled. Default: 0.

**Size**: 1 byte dec

### Dimmer Basic Set Custom Brightness On

**Parameter 37**: Set custom brightness (or leave last brightness) for for Basic Set ON commands when the dimmer is triggered by another device in direct association.

**Values**: 0 – last brightness level; 1-99 (%). Default: 0.

**Size**: 1 byte dec

### Dimmer Gamma Factor

**Parameter 38**: Adjust the gamma factor for the dimmer to improve dimming performance (experts only).

The gamma factor in a dimmer setting defines how the output brightness responds to input control changes, shaping the perceived light intensity. A higher gamma makes dimming more gradual at low levels, while a lower gamma results in a more linear or abrupt transition.

**Values**: 10-50 = 1.0 – 5.0 gamma. Default: 22.

**Size**: 1 byte dec

### Relay Scene Control Multi-Tap

**Parameter 39**: Disable multi-tap scene control for the relay so that only single taps report via central scene.

Once this functionality is disabled, double taps, held, released, 3-tap, 4-tap, and 5-tap scene events will be ignored when the relay is physically pressed or tapped and won't be reported to the hub.

**Values**: 0 – multi-tap for scene control enabled; 1 – multi-tap for scene control disabled. Default: 0.

**Size**: 1 byte dec

### Dimmer Scene Control Multi-Tap

**Parameter 40**: Disable multi-tap scene control for the dimmer paddles so that only single taps report via central scene.

Once this functionality is disabled, double taps, held, released, 3-tap, 4-tap, and 5-tap scene events will be ignored when the dimmer paddles are physically pressed or tapped and won't be reported to the hub.

**Values**: 0 – multi-tap for scene control enabled; 1 – multi-tap for scene control disabled. Default: 0.

**Size**: 1 byte dec

### Relay LED Indicator Multi-Color

**Parameter 41**: Choose the color of the LED indicator for the relay in opposite switch state (instead of off) when the LED indicator mode (parameter 2) is set to values 0 or 1. The color chosen in this setting will apply instead of the default "off" value (LED doesn't light up).

**Values**: 0 – off; 1 – white; 2 – blue; 3 – green; 4 – red. Default: 0.

**Size**: 1 byte dec

### Dimmer LED Indicator Multi-Color

**Parameter 42**: Choose the color of the LED indicator for the dimmer in opposite switch state (instead of off) when the LED indicator mode (parameter 2) is set to values 0 or 1. The color chosen in this setting will apply instead of the default "off" value (LED doesn't light up).

**Values**: 0 – off; 1 – white; 2 – blue; 3 – green; 4 – red. Default: 0.

**Size**: 1 byte dec

### How to Access the Advanced Settings

[How to Access the Advanced Settings for the ZEN30 on Home Assistant](https://www.support.getzooz.com/kb/article/491-how-to-access-the-advanced-settings-for-your-zen30-double-switch-on-home-assistant/)

[How to Access the Advanced Settings for the ZEN30 on HomeSeer](https://www.support.getzooz.com/kb/article/1800-how-to-access-the-advanced-settings-for-zen30-double-switch-on-homeseer/)

[How to Access the Advanced Settings for the ZEN30 on Hubitat](https://www.support.getzooz.com/kb/article/384-how-to-access-advanced-settings-for-zen30-double-switch-on-hubitat/)

[How to Access the Advanced Settings for the ZEN30 on SmartThings](https://www.support.getzooz.com/kb/article/383-how-to-access-advanced-settings-for-zen30-double-switch-on-smartthings/)

[How to Access the Advanced Settings for the ZEN30 on Z-Box](https://www.support.getzooz.com/kb/article/1606-how-to-access-advanced-settings-for-my-zen30-double-switch-on-z-box/)

### Central Scene Mapping

**Dimmer Upper Paddle:**

1 x tap: load on to last / custom brightness; Scene 1, attribute 00

2 x tap: on to full / max brightness; Scene 1, attribute 03

3 x tap: enter inclusion (pairing) mode; Scene 1, attribute 04

4 x tap: Scene 1, attribute 05

5 x tap: Scene 1, attribute 06

6 x tap: change LED indicator mode (see parameter 1)

press and hold: increase brightness level; Scene 1, attribute 02

release: Scene 1, attribute 01

**Lower Paddle:**

1 x tap: load off; Scene 2, attribute 00

2 x tap: Scene 2, attribute 03

3 x tap: enter exclusion (unpairing) mode; Scene 2, attribute 04

4 x tap: Scene 2, attribute 05

5 x tap: Scene 2, attribute 06

press and hold: decrease brightness level; Scene 2, attribute 02

release: Scene 2, attribute 01

tap-tap-tap-tap-and-hold: change physical / Z-Wave control mode (see parameter 19)

hold for 15 seconds: initiate factory reset (then release and hold the **upper** paddle to complete the reset)

**Relay Button:**

1 x tap: load on / off; Scene 3, attribute 00

2 x tap: Scene 3, attribute 03

3 x tap: enter inclusion (pairing) mode; Scene 3, attribute 04

4 x tap: Scene 3, attribute 05

5 x tap: Scene 3, attribute 06

6 x tap: change LED indicator mode (see parameter 2)

press and hold: increase brightness level; Scene 3, attribute 02

release: Scene 3, attribute 01

### Supported Command Classes

COMMAND\_CLASS\_ZWAVEPLUS\_INFO

COMMAND\_CLASS\_SWITCH\_MULTILEVEL

COMMAND\_CLASS\_SWITCH\_BINARY

COMMAND\_CLASS\_ASSOCIATION

COMMAND\_CLASS\_MULTI\_CHANNEL\_ASSOCIATION

COMMAND\_CLASS\_ASSOCIATION\_GRP\_INFO

COMMAND\_CLASS\_TRANSPORT\_SERVICE

COMMAND\_CLASS\_VERSION

COMMAND\_CLASS\_MANUFACTURER\_SPECIFIC

COMMAND\_CLASS\_DEVICE\_RESET\_LOCALLY

COMMAND\_CLASS\_POWERLEVEL

COMMAND\_CLASS\_CONFIGURATION

COMMAND\_CLASS\_CENTRAL\_SCENE

COMMAND\_CLASS\_MULTI\_CHANNEL

COMMAND\_CLASS\_SECURITY\_2

COMMAND\_CLASS\_SUPERVISION

COMMAND\_CLASS\_FIRMWARE\_UPDATE\_MD

All ZEN30 switches can be updated via OTA firmware updates, [here is how to do that](http://www.support.getzooz.com/kb/article/253-how-to-perform-an-ota-firmware-update-on-zooz-devices/). You can [access all firmware files here](https://www.support.getzooz.com/kb/article/1158-zooz-ota-firmware-files/). There are currently 4 different hardware versions (1.0, 2.0, 3.0, and 4.0) of the product so you need to make sure to apply the correct firmware for your version. Questions? Just [reach out](https://www.support.getzooz.com/new/) to our tech support team.