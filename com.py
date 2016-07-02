"""The network module."""
import struct
import select
import socket
import threading
import time
import base64
import atexit
import errno


PREFIX_FORMAT = "!I"
PREFIX_LENGTH = struct.calcsize(PREFIX_FORMAT)

RSTATE_PREFIX = "prefix"
RSTATE_BODY = "body"

BROADCAST_IDENTIFIER = "HIDrem0:1"
BROADCAST_PORT = 5026
BROADCAST_INTERVAL = 1
assert "|" not in BROADCAST_IDENTIFIER


def discover(searchtime=3):
	s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
	s.bind(("", BROADCAST_PORT))
	s.settimeout(searchtime)
	starttime = time.time()
	found = []
	while time.time() - starttime <= searchtime:
		try:
			data, address = s.recvfrom(2048)
		except socket.timeout:
			# check wether searchtime was exceeded
			continue
		ip = address[0]
		if not data.startswith(BROADCAST_IDENTIFIER):
			continue
		data = data.replace(BROADCAST_IDENTIFIER + "|", "", 1)
		tdata = []
		tdata = data.split("|")
		tdata[0] = base64.b64decode(tdata[0])
		tdata[1] = ip
		tdata[2] = int(tdata[2])
		tdata = tuple(tdata)
		if tdata not in found:
			found.append(tdata)
	try:
		s.close()
	except:
		pass
	return found


def broadcast(port):
	s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
	s.bind(("", 0))
	atexit.register(s.close)
	s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
	try:
		ip = socket.gethostbyname(socket.gethostname())
	except:
		try:
			ip = socket.gethostbyname(socket.getfqdn())
		except:
			raise Exception("Cannot broadcast IP: reason: IP unknown!")
	hostname = base64.b64encode(socket.gethostname())
	try:
		while True:
			msg = BROADCAST_IDENTIFIER + "|" + hostname + "|" + ip + "|" + str(port)
			s.sendto(msg, ("<broadcast>", BROADCAST_PORT))
			time.sleep(BROADCAST_INTERVAL)
	finally:
		s.close()


class LengthPrefixedReceiver(object):
	"""this class handles the receiving and sending of messages."""
	def __init__(self, manager, peer):
		self.manager = manager
		self._peer = peer
		self.reset_receive()
		self.setup()

	def setup(self):
		"""called on __init__"""
		pass
		
	def reset_receive(self):
		"""resets the receive state."""
		self._recv_state = RSTATE_PREFIX
		self._buffer = ""
		self._to_recv = PREFIX_LENGTH
		
	def feed(self, data):
		"""feeds data to the receiver."""
		while len(data) > 0:
			self._buffer += data[:min(self._to_recv, len(data))]
			if self._to_recv > len(data):
				self._to_recv -= len(data)
				data = ""
			else:
				data = data[self._to_recv:]
				if self._recv_state == RSTATE_PREFIX:
					self._to_recv = struct.unpack(PREFIX_FORMAT, self._buffer)[0]
					self._buffer = ""
					if self._to_recv > 0:
						self._recv_state = RSTATE_BODY
					else:
						self._recv_state = RSTATE_PREFIX
						self._to_recv = PREFIX_LENGTH
				elif self._recv_state == RSTATE_BODY:
					self._to_recv = PREFIX_LENGTH
					self._recv_state = RSTATE_PREFIX
					msg = self._buffer
					self._buffer = ""
					self.got_message(msg)
				else:
					raise RuntimeError("Unknown state!")
					
	def got_message(self, msg):
		"""called with a received message."""
		pass
	
	def send_message(self, msg):
		"""sends a message to peer."""
		length = len(msg)
		prefix = struct.pack(PREFIX_FORMAT, length)
		tosend = prefix + msg
		self.manager.send_message(self._peer, tosend)
	
	def on_close(self, error):
		"""called when the connection is close"""
		pass
	
	def close(self):
		"""closes the socket."""
		self.manager.close(self)


class ConnectionManager(object):
	"""The ConnectionManager manages connections."""
	select_timeout = 0.1
	max_read = 2048
	max_write = 2048
	
	def __init__(self, debug=False):
		self.debug = debug
		self._running = False
		self.listen_s = {}  # socket() -> proto
		self.s2r = {}  # socket() -> proto()
		self.s2w = {}  # socket() -> data
		self.slock = threading.Lock()
	
	def listen(self, host, port, proto):
		"""create a socket, bind to (host, port) and
		create a proto() for all incoming connections.
		returns the port listening on."""
		s = socket.socket()
		s.bind((host, port))
		s.listen(1)
		self.slock.acquire()
		self.listen_s[s] = proto
		self.slock.release()
		port = s.getsockname()[1]
		if self.debug:
			print("Now listening on port {p}.".format(p=port))
		return port
	
	def connect(self, address, proto):
		"""create a proto() with a socket() connected to address."""
		assert isinstance(address, tuple)
		if self.debug:
			print("Connecting to '{a}'...".format(a=address))
		s = socket.socket()
		s.connect(address)
		pi = proto(self, s)
		self.slock.acquire()
		self.s2r[s] = pi
		self.s2w[s] = ""
		self.slock.release()
		if self.debug:
			print("Connected.")
		return pi
		
	def run(self):
		"""runs the mainloop."""
		if self._running:
			raise RuntimeError("Already Running!")
		self._running = True
		if self.debug:
			print("Entering Mainloop...")
		while self._running:
			self.slock.acquire()
			ls = self.listen_s.keys()
			rs = self.s2r.keys()
			ws = filter(None, [s if self.s2w[s] else None for s in self.s2w.keys()])
			es = ls + ws + rs
			self.slock.release()
			if len(ls + rs + ws + es) == 0:
				# dont select() without sockets
				time.sleep(self.select_timeout)
				continue
			try:
				tr, tw, he = select.select(ls + rs, ws, es, self.select_timeout)
			except select.error as e:
				if e.args[0] == errno.EBADF:
					# reload select list
					continue
				else:
					raise
			
			for s in he:
				if self.debug:
					print("Error in socket on '{a}'!".format(a=s.getsockname()))
				if s in ls:
					try:
						s.close()
					except:
						pass
					self.slock.acquire()
					del self.listen_s[s]
					self.slock.release()
				else:
					self.slock.acquire()
					proto = self.s2r[s]
					self.slock.release()
					proto.on_close(True)
					self.slock.acquire()
					del self.s2r[s]
					del self.s2w[s]
					self.slock.release()
			
			for s in tr:
				# data aviable
				if s in ls:
					# incomming connection
					if self.debug:
						print("Got connection on '{a}'.".format(a=s.getsockname()))
					self.slock.acquire()
					protoclass = self.listen_s[s]
					self.slock.release()
					client = s.accept()[0]
					proto = protoclass(self, client)
					self.slock.acquire()
					self.s2r[client] = proto
					self.s2w[client] = ""
					self.slock.release()
				else:
					# incomming data
					if self.debug:
						print("Data received on '{a}'.".format(a=s.getsockname()))
					self.slock.acquire()
					proto = self.s2r[s]
					self.slock.release()
					data = s.recv(self.max_read)
					if self.debug:
						print("Received {n} bytes.".format(n=len(data)))
					if data:
						proto.feed(data)
					else:
						if self.debug:
							print("Socket on '{a}' was closed.".format(a=s.getsockname()))
						proto.on_close(False)
						self.slock.acquire()
						del self.s2r[s]
						del self.s2w[s]
						self.slock.release()
						try:
							s.close()
						except:
							pass
			for s in tw:
				# can write data to socket
				self.slock.acquire()
				buff = self.s2w[s]
				if len(buff) == 0:
					self.slock.release()
					continue
				if self.debug:
					print("Writing data to '{a}'".format(a=s.getsockname()))
				if len(buff) >= self.max_write:
					tosend = buff
					self.s2w[s] = ""
				else:
					tosend = buff[:self.max_write]
					self.s2w[s] = buff[self.max_write:]
				s.send(tosend)
				self.slock.release()
	
	def send_message(self, target, message):
		"""sends a message to target."""
		self.slock.acquire()
		self.s2w[target] += message
		self.slock.release()
	
	def close(self, protocol):
		"""closes the given protocol."""
		self.slock.acquire()
		s = None
		for os in self.s2r:
			if self.s2r[os] is protocol:
				s = os
				break
		if not s:
			self.slock.release()
			raise ValueError("No such protocol connected!")
		if self.debug:
			print("Closing protocol on '{a}'.".format(a=s.getsockname()))
		protocol.on_close(False)
		try:
			s.close()
		except:
			pass
		del self.s2r[s]
		del self.s2w[s]
		self.slock.release()
			
	def stop(self):
		"""stops the mainloop"""
		if not self._running:
			raise RuntimeError("Not running!")
		self._running = False
	
	def start(self):
		"""starts the mainloop in another Thread."""
		if self._running:
			raise RuntimeError("Already running!")
		thr = threading.Thread(name="ConnectionManagerLoop", target=self.run)
		thr.daemon = True
		thr.start()
