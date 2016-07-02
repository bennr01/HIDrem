#!python2
"""This script allows you to connect to a HIDremServer
and emulate HID devices on it."""
import atexit
import socket
import time
import threading
import json
import os

import ui
import dialogs
import scene
import console
from objc_util import on_main_thread

import com
import common

# settings
DEBUG = False
KEYMAPPATH = os.path.join(os.getcwd(), "keymaps")

# messages for dialogs
MSG_DIRECT_CONNECT = "Direct Connect"
MSG_NEW_KEYMAP = "Create new Keymap"

# keymap type identifiers
TYPE_NBUTTON = "BoolButton"
TYPE_PBUTTON = "PressureButton"
TYPE_VECTOR = "2DInput"


@on_main_thread
def ask_disconnect():
	try:
		b = console.alert("Connection", "Already connected.", "Disconnect")
		return b == 1
	except KeyboardInterrupt:
		return False


class Keymap(object):
	"""stores an keymap."""
	def __init__(self, name, map={}):
		self.name = name
		self.map = map
		self.path = os.path.join(KEYMAPPATH, name)
	
	@classmethod
	def load(cls, name):
		"""load a keymap from the path."""
		path = os.path.join(KEYMAPPATH, name)
		with open(path, "rU") as fin:
			map = json.load(fin)
		return cls(name, map)
	
	def save(self):
		"""saves the keymap to path."""
		with open(self.path, "w") as f:
			json.dump(self.map, f)
	
	def __getitem__(self, key):
		"""returns the corresponding value or None if not found."""
		if key not in self.map:
			return None
		else:
			info = self.map[key]
			return info
	
	def __setitem__(self, key, value):
		"""sets the key to value."""
		self.map[key] = value
		self.save()
	
	def __delitem__(self, key):
		"""deletes a key"""
		del self.map[key]
		self.save()


class ControllScene(scene.Scene):
	"""The ControlScene handles input events."""
	def __init__(self, client):
		scene.Scene.__init__(self)
		self.client = client
		self.show_nctrl = False
		self.show_nconn = False
		self.show_ping = False
		self.labelnode = scene.LabelNode()  # not in setup() because
		# update_label() is called before setup()
	
	def setup(self):
		self.background_color = self.client.background_color
		self.add_child(self.labelnode)
		self.labelnode.position = self.size / 2.0
		self.labelnode.color = "#ff0000"
		self.check_controller()

	def check_controller(self):
		"""checks wether an controller is connected."""
		controllers = scene.get_controllers()
		if len(controllers) == 0:
			self.show_nctrl = True
			self.update_label()
			return False
		else:
			self.show_nctrl = False
			self.update_label()
			return True
	
	def controller_changed(self, _, key, value,):
		"""called when the controller is changed."""
		if key == "connected":
			self.check_controller()
			if not value:
				# workaround for still detected controllers
				self.show_nctrl = True
				self.update_label()
		else:
			self.client.proxy.controller_changed(key, value)
	
	def set_ping(self, ms):
		"""called when a ping result was received."""
		text = str(ms) + "ms"
		if self.show_ping:
			self.labelnode.text = text
		else:
			self.update_label()
	
	def update_label(self):
		"""checks what text needs to be shown by the labelnode."""
		if self.show_nctrl:
			self.show_ping = False
			self.labelnode.text = "No Controller found!"
		elif self.show_nconn:
			self.show_ping = False
			self.labelnode.text = "Not connected!"
		else:
			self.show_ping = True
		

class CCProxy(object):
	"""a object used for dynamically direct the controller actions."""
	def __init__(self):
		self.default_receiver = None
		self.receiver = None
	
	def controller_changed(self, key, value):
		"""redirect an event."""
		if self.receiver is not None:
			self.receiver.controller_changed(key, value)
		elif self.default_receiver is not None:
			self.default_receiver.controller_changed(key, value)
		else:
			pass
	
	def set_focus(self, receiver):
		"""set proxy to redirect events to receiver."""
		self.receiver = receiver
	
	def lose_focus(self, who=None):
		"""set proxy to redirect events to default_proxy.
		Does not do anything if who is not None and is not the currently focussed."""
		if (who is not None) and (who is not self.receiver):
			return
		self.receiver = None


class HIDremClientProtocol(com.LengthPrefixedReceiver):
	"""Client Side protocol."""
	def setup(self):
		self.root = None
	
	def ping(self):
		"""starts a ping."""
		t = time.time()
		self.send_message(common.ID_PING + str(t))
	
	def got_message(self, msg):
		"""called when a message was received."""
		if not msg:
			return
		idb, msg = msg[0], msg[1:]
		if idb == common.ID_PING:
			now = time.time()
			last = float(msg)
			passed = now - last
			ms = int(round(passed / 2.0, 4) * 1000)
			self.root.got_ping(ms)
	
	def on_close(self, error=False):
		"""called when the protocol was closed."""
		self.root.connected = False
		self.root.proto = None
		self.root.controller.show_nconn = True
	
	def press_key(self, key):
		"""presses a key on the keyboard."""
		msg = common.ID_KEYBOARD + common.ACTION_PRESS + key
		self.send_message(msg)
	
	def release_key(self, key):
		"""releases a key on the keyboard."""
		msg = common.ID_KEYBOARD + common.ACTION_RELEASE + key
		self.send_message(msg)


class HIDremClientView(ui.View):
	"""a ui.View for a HIDrem client."""
	def __init__(self):
		# ui setup
		ui.View.__init__(self)
		self.connected = False
		self.proto = None
		self.background_color = "#000000"
		self.cmb = ui.Button()
		self.conb = ui.Button()
		self.sceneholder = scene.SceneView()
		self.AI = ui.ActivityIndicator()
		self.controller = ControllScene(self)
		self.sceneholder.background_color = self.background_color
		self.cmb.image = ui.Image('iob:game_controller_b_256')
		self.conb.image = ui.Image('iob:wifi_256')
		self.add_subview(self.cmb)
		self.add_subview(self.conb)
		self.add_subview(self.sceneholder)
		self.add_subview(self.AI)
		self.cmb.border_width = self.conb.border_width = 2
		self.cmb.border_color = self.conb.border_color = '#ff0000'
		self.cmb.tint_color = self.conb.tint_color = "#ff0000"
		self.cmb.corner_radius = self.conb.corner_radius = 15
		self.cmb.flex = self.conb.flex = "TBHLRW"
		self.sceneholder.flex = "TBHLRW"
		y = self.height / 2.0
		midx = self.width / 2.0
		width = (5.0 / 16.0) * self.width
		offset = (1.0 / 6.0) / 2.0 * self.width
		height = (1.0 / 2.0) * self.height
		y = (self.height - height) / 2.0
		cmbx = midx - offset - width
		conbx = midx + offset
		self.cmb.frame = (cmbx, y, width, height)
		self.conb.frame = (conbx, y, width, height)
		self.sceneholder.frame = (0, self.height - y, self.width, y)
		self.sceneholder.frame_interval = 4
		self.sceneholder.anti_alias = True
		self.sceneholder.shows_fps = False
		self.sceneholder.scene = self.controller
		self.AI.style = ui.ACTIVITY_INDICATOR_STYLE_WHITE_LARGE
		self.AI.hides_when_stopped = True
		self.AI.frame = (
			midx - offset,
			self.height/2.0 - offset,
			offset * 2,
			offset * 2
			)
		self.AI.flex = "TBHLRW"
		self.controller.show_nconn = True
		self.controller.update_label()
		
		# conn setup
		self.manager = com.ConnectionManager(debug=DEBUG)
		
		# other setup
		self.proxy = CCProxy()
		self.proxy.default_receiver = self
		self.cmb.action = self.show_cmb_setup
		self.conb.action = self.show_connection_setup
		
		self.bthr = threading.Thread(
			name="Background jobs",
			target=self.background_thread
			)
		self.bthr.daemon = True
		self.bthr.start()
		
		if not os.path.exists(KEYMAPPATH):
			os.mkdir(KEYMAPPATH)
		
		try:
			self.keymap = Keymap.load("default")
		except IOError:
			self.keymap = Keymap("default", {})
			self.keymap.save()
	
	def controller_changed(self, key, value):
		"""called when the state of a key on the controller changes."""
		if not (self.connected and (self.proto is not None)):
			return
		info = self.keymap[key]
		if info is None:
			return
		intype = info["type"]
		if intype == TYPE_NBUTTON:
			kbb = info["button"]
			if len(kbb) == 0:
				return
			if value:
				self.proto.press_key(kbb)
			else:
				self.proto.release_key(kbb)
		elif intype == TYPE_PBUTTON:
			kbb = info["button"]
			trigger = info["trigger"]
			if value >= trigger:
				self.proto.press_key(kbb)
			else:
				self.proto.release_key(kbb)
		elif intype == TYPE_VECTOR:
			deadzone = info["trigger"]
			x = value.x
			y = value.y
			upb = info["upbutton"]
			downb = info["downbutton"]
			leftb = info["leftbutton"]
			rightb = info["rightbutton"]
			if y > deadzone:
				self.proto.press_key(upb)
			else:
				self.proto.release_key(upb)
			if y < (deadzone * -1):
				self.proto.press_key(downb)
			else:
				self.proto.release_key(downb)
			if x > deadzone:
				self.proto.press_key(rightb)
			else:
				self.proto.release_key(rightb)
			if x < (deadzone * -1):
				self.proto.press_key(leftb)
			else:
				self.proto.release_key(leftb)
	
	@ui.in_background
	def show_cmb_setup(self, sender):
		"""shows the user a view to setup the controller keymap."""
		keymapname = dialogs.list_dialog(
			"Select Keymap",
			[MSG_NEW_KEYMAP] + os.listdir(KEYMAPPATH),
			False
			)
		if keymapname is None:
			return
		if keymapname == MSG_NEW_KEYMAP:
			self.new_keymap()
		else:
			try:
				keymap = Keymap.load(keymapname)
			except:
				console.alert(
					"Error",
					"Cannot load Keymap!",
					"Ok",
					hide_cancel_button=True
					)
				return
			try:
				choice = console.alert(
					keymapname,
					"",
					"Select",
					"Edit",
					"Delete"
					)
			except KeyboardInterrupt:
				return
			if choice == 1:
				self.map = keymap
			elif choice == 2:
				self.edit_keymap(keymap)
			elif choice == 3:
				try:
					console.alert(
						"Sure?",
						"Are you sure you want to delete this keymap?",
						"Delete"
						)
				except KeyboardInterrupt:
					return
				os.remove(os.path.join(KEYMAPPATH, keymapname))
	
	@ui.in_background
	def new_keymap(self):
		"""creates a new keymap."""
		try:
			keymapname = console.input_alert(
				"Create new Keymap",
				"Please enter the name of the new Keymap.",
				"",
				"Create"
				)
		except KeyboardInterrupt:
			return
		if len(keymapname) == 0 or keymapname == MSG_NEW_KEYMAP:
			console.alert(
				"Please enter a name for the Keymap!",
				"",
				"Ok",
				hide_cancel_button=True
				)
			return
		if keymapname in os.listdir(KEYMAPPATH):
			console.alert(
				"Error",
				"A Keymap with this name already exists!",
				"Ok",
				hide_cancel_button=True
				)
			return
		keymap = Keymap(keymapname, {})
		self.edit_keymap(keymap)
	
	def edit_keymap(self, keymap):
		"""edit the keymap."""
		editor = KeymapEditor(self, keymap)
		editor.present(
			"fullscreen",
			orientations=("landscape",),
			hide_title_bar=True
			)
		
	@ui.in_background
	def show_connection_setup(self, sender):
		"""shows the user a view to setup the connection."""
		if self.connected:
			do_disconnect = ask_disconnect()
			if do_disconnect:
				self.disconnect()
			else:
				return
		else:
			servers = self.discover()
			addresses = [a[1] + ":" + str(a[2]) for a in servers]
			to_show = [MSG_DIRECT_CONNECT] + addresses
			selected = dialogs.list_dialog(
				title="Select Server",
				items=to_show,
				multiple=False
				)
			if selected is None:
				return
			elif selected is MSG_DIRECT_CONNECT:
				self.do_direct_connect()
			else:
				self.connect(selected)
	
	def discover(self):
		"""discovers servers."""
		try:
			self.AI.start()
			servers = com.discover(searchtime=3)
			return servers
		finally:
			self.AI.stop()
		
	def run(self):
		"""runs the client."""
		console.show_activity()
		self.manager.start()
		self.present(
			style="fullscreen",
			orientations=("landscape", ),
			hide_title_bar=True
			)
		atexit.register(self.on_quit)
		
	def on_quit(self):
		"""called at exit."""
		self.manager.stop()
		console.hide_activity()
	
	def disconnect(self):
		"""disconnects."""
		assert self.connected
		self.proto.close()
		self.connected = False
		self.proto = None
		self.controller.show_nconn = True
		self.controller.update_label()
	
	def connect(self, addr):
		"""connect to target server."""
		try:
			addrtuple = addr.split(":")
			addrtuple = socket.gethostbyname(addrtuple[0]), int(addrtuple[1])
		except:
			console.alert("Error", "Invalid Address!", "Ok", hide_cancel_button=True)
			return
		try:
			self.proto = self.manager.connect(addrtuple, HIDremClientProtocol)
			self.proto.root = self
			self.connected = True
			self.controller.show_nconn = False
			self.controller.update_label()
		except Exception as e:
			self.connected = False
			console.alert("Error", e.message, "Ok", hide_cancel_button=True)
			return
	
	def do_direct_connect(self):
		"""prompt the user for an address and connects there."""
		try:
			addr = console.input_alert(
				"Direct Connect",
				"Please enter the IP:PORT you want to connect to.",
				"",
				"Connect"
				)
		except KeyboardInterrupt:
			return
		self.connect(addr)
	
	def background_thread(self):
		"""code which needs to run in the background."""
		while True:
			time.sleep(1)
			if self.proto is not None:
				self.proto.ping()
	
	def got_ping(self, ms):
		"""called when a ping result was received."""
		self.controller.set_ping(ms)


class KeymapEditor(ui.View):
	"""The keymap editor."""
	def __init__(self, root, keymap):
		ui.View.__init__(self)
		self.root = root
		self.keymap = keymap
		self.smb = ui.Label()
		self.smb.alpha = 1
		self.smb.text_color = '#dcdcdc'
		self.smb.text = "Press a button or use a joystick"
		self.smb.alignment = ui.ALIGN_CENTER
		self.background_color = "#ffffff"
		self.cs = self.smb
		self.show(self.smb)
		self.quitbutton = ui.Button()
		self.quitbutton.action = self.quit
		self.quitbutton.tint_color = "#ff0000"
		self.quitbutton.title = "Quit"
		self.quitbutton.flex = "WHLRTB"
		self.add_subview(self.quitbutton)
		x, y, w, h = self.bounds
		self.quitbutton.frame = (
			x,
			y + h * 0.9,
			w,
			h * 0.1
			)
		self.root.proxy.set_focus(self)
	
	def show(self, view):
		"""shows the current view."""
		self.cs.send_to_back()
		self.remove_subview(self.cs)
		self.add_subview(view)
		x, y, w, h = self.bounds
		nh = h * 0.9
		ny = h * 0.1
		view.frame = (x, ny, w, nh)
		view.flex = "WHLRTB"
		self.cs = view
	
	def quit(self, sender=None):
		"""closes the view."""
		self.root.proxy.lose_focus()
		self.keymap.save()
		self.close()
		self.root.keymap = self.keymap
	
	@ui.in_background
	def controller_changed(self, key, value):
		"""called when a button was pressed."""
		oldvalue = self.keymap[key]
		self.root.proxy.lose_focus()
		try:
			if isinstance(value, bool):
				intype = TYPE_NBUTTON
				if not value:
					return
			elif isinstance(value, float):
				intype = TYPE_PBUTTON
				if value < 0.7:
					return
			elif isinstance(value, scene.Point):
				intype = TYPE_VECTOR
				if abs(value) < 0.7:
					return
			if oldvalue is not None:
				if oldvalue["type"] != intype:
					oldvalue = None
					del self.keymap[key]
			
			ac = ui.AUTOCAPITALIZE_NONE
			ack = "autocapitalization"
			
			if intype == TYPE_NBUTTON:
				fields = [
					{
						"type": "text",
						"value": "Normal Button",
						"title": "Type",
						},
					{
						"type": "text",
						"value": oldvalue["button"] if oldvalue else "",
						"title": "Keyboard Button",
						"key": "keyboardbutton",
						ack: ac,
						}
					
					]
			
			elif intype == TYPE_PBUTTON:
				fields = [
					{
						"type": "text",
						"value": "Pressure-sensitive Button",
						"title": "Type",
						},
					{
						"type": "text",
						"value": oldvalue["button"] if oldvalue else "",
						"title": "Keyboard Button",
						"key": "keyboardbutton",
						ack: ac,
						},
					{
						"type": "number",
						"value": str(oldvalue["trigger"]) if oldvalue else "0.5",
						"title": "Trigger on",
						"key": "trigger",
					}
					]
			elif intype == TYPE_VECTOR:
				fields = [
					{
						"type": "text",
						"value": "Directional Input",
						"title": "Type",
						},
					{
						"type": "number",
						"value": str(oldvalue["trigger"]) if oldvalue else "0.5",
						"title": "Deadzone",
						"key": "trigger",
						},
					{
						"title": "Upwards-Button",
						"type": "text",
						"key": "upbutton",
						"value": oldvalue["upbutton"] if oldvalue else "",
						ack: ac,
					},
					{
						"title": "Downwards-Button",
						"type": "text",
						"key": "downbutton",
						"value": oldvalue["downbutton"] if oldvalue else "",
						ack: ac,
					},
					{
						"title": "Leftwards-Button",
						"type": "text",
						"key": "leftbutton",
						"value": oldvalue["leftbutton"] if oldvalue else "",
						ack: ac,
					},
					{
						"title": "Rightwards-Button",
						"type": "text",
						"key": "rightbutton",
						"value": oldvalue["rightbutton"] if oldvalue else "",
						ack: ac,
					},
					]
			
			res = dialogs.form_dialog("Mapping: " + key, fields)
			if res is None:
				return
			
			if intype == TYPE_NBUTTON:
				kbb = res["keyboardbutton"]
				self.keymap[key] = {
					"type": intype,
					"button": kbb,
					}
				return
			elif intype == TYPE_PBUTTON:
				kbb = res["keyboardbutton"]
				tv = res["trigger"]
				try:
					tv = float(tv.replace(",", "."))
					if tv < 0.0 or tv > 1.0:
						raise ValueError
				except ValueError:
					console.alert(
						"Invalid Input",
						"Please enter a number between 0 and 1!",
						"Ok",
						hide_cancel_button=True
						)
					return
				self.keymap[key] = {
					"type": intype,
					"button": kbb,
					"trigger": tv
					}
				return
			elif intype == TYPE_VECTOR:
				upb = res["upbutton"]
				downb = res["downbutton"]
				leftb = res["leftbutton"]
				rightb = res["rightbutton"]
				tv = res["trigger"]
				try:
					tv = float(tv.replace(",", "."))
					if tv < 0.0 or tv > 1.0:
						raise ValueError
				except ValueError:
					console.alert(
						"Invalid Input",
						"Please enter a number between 0 and 1!",
						"Ok",
						hide_cancel_button=True
						)
					return
				self.keymap[key] = {
					"type": intype,
					"trigger": tv,
					"upbutton": upb,
					"downbutton": downb,
					"leftbutton": leftb,
					"rightbutton": rightb,
					}
				return
		finally:
			self.root.proxy.set_focus(self)

if __name__ == "__main__":
	HIDremClientView().run()
