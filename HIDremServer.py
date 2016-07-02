"""The server module for HIDrem."""
import threading

from pymouse import PyMouse
from pykeyboard import PyKeyboard

import common
import com


class HIDremServerProtocol(com.LengthPrefixedReceiver):
	"""The communication protocol."""
	def setup(self):
		self.k = PyKeyboard()
		self.m = PyMouse()
	
	def got_message(self, msg):
		"""called when a message was received."""
		if not msg:
			return
		idb, msg = msg[0], msg[1:]
		if idb == common.ID_PING:
			# echo message
			self.send_message(idb + msg)
		elif idb == common.ID_KEYBOARD:
			action, keyname = msg[0], msg[1:]
			if action == common.ACTION_PRESS:
				self.k.press_key(keyname)
			elif action == common.ACTION_RELEASE:
				self.k.release_key(keyname)
			else:
				# protocol violation
				self.close()
		elif idb == common.ID_MOUSE:
			pass
		else:
			# protocol violation
			self.close()


class HIDremServer(object):
	"""The Server."""
	def __init__(self):
		self.manager = com.ConnectionManager()
		self.port = self.manager.listen("0.0.0.0", 0, HIDremServerProtocol)
	
	def run(self):
		"""enters the mainloop and start background jobs."""
		thr = threading.Thread(
			name="Broadcasting Thread",
			target=com.broadcast,
			args=(self.port, )
			)
		thr.daemon = True
		thr.start()
		self.manager.run()


if __name__ == "__main__":
	server = HIDremServer()
	server.run()
