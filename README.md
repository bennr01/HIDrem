# HIDrem
Use the Pythonista App + MFi-Controller to emulate HID-devices on a Computer

##What is HIDrem
HIDrem uses a Server on your Computer to emulate a Keyboard and a mouse which can be accessed by the clients.
The HIDremClient uses The Pythonista programming App for iOS to press these Keys corresponding to the configurtion of the client.

##Requirements (Server):
- [Python 2.x] (https://python.org/)
- [PyUserInput](https://github.com/PyUserInput/PyUserInput)
- Network connection

##Requirements (Client):
- [Pythonista 3](https://itunes.apple.com/de/app/pythonista-3/id1085978097?mt=8) (2.1 should also work)
- Network connection
- MFi-Controller/Gamepad

##Install (Server)
1. Install Python 2
2. `pip install PyUserInput`
3. download `HIDremServer.py`, `common.py` and `com.py` into the same folder

##Install (Client)
1. Download Pythonista
2. Install a GitHub Tool or [StaSh](https://github.com/ywangd/stash)
3. Clone this repo

##Run (Server)
Type `python HIDremServer.py` in a console in the folder

##Run (Client)
1. Start Pythonista (3)
2. run `HIDremClient.py`

##Usage
1. Start Server
2. Start Client
3. Connect Controller
4. Press the right button to search for servers. If None could be found, use direct connect (IP:PORT).
5. Press the left button to create or select a keymap
5. Have Fun!

##Tips

- You can enter the name of special keys (like shift). You only need to enter them into the keyboardbutton field. See PyUserInput for more information.
