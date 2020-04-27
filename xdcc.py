import irc.client
import struct
import sys
from time import time
import shlex
import os
import argparse
import itertools
import random
import signal

ERASE_LINE = '\x1b[2K'

def hour_min_second(seconds):
    minutes, seconds = divmod(seconds,60)
    hours, minutes = divmod(minutes, 60)
    return "%02d:%02d:%02d" % (hours, minutes, seconds)

class DCCcat(irc.client.SimpleIRCClient):
    def __init__(self, args):
        irc.client.SimpleIRCClient.__init__(self)
        self.args = args
        self.received_bytes = 0

        self.total_size = 0
        self.last_received_bytes = 0
        self.last_print_time = 0


    def on_ctcp(self, connection, event):
        if event.arguments[0] != "DCC":
            return

        payload = event.arguments[1]
        parts = shlex.split(payload)
        command, filename, peer_address, peer_port, size = parts
        if command != "SEND":
            return

        self.filename = os.path.basename(filename)
        self.file = sys.stdout if self.args.stdout else  open(self.filename, "wb")

        self.total_size = int(size)
        peer_address = irc.client.ip_numstr_to_quad(peer_address)
        peer_port = int(peer_port)
        self.dcc = self.dcc_connect(peer_address, peer_port, "raw")

    def show_download_status(self):
        now = time()
        if now - self.last_print_time >= 1:
            percentage = 100*self.received_bytes/self.total_size
            speed = (self.received_bytes - self.last_received_bytes)
            erase_line_msg = '\r' + ERASE_LINE
            duration = hour_min_second((self.total_size - self.received_bytes)/speed)
            print(erase_line_msg + "%s: (%.2f%%) [%.2f MB/s] {%s}" % (self.filename,percentage,speed/(1e6),duration), end='')
            sys.stdout.flush()

            self.last_print_time = now
            self.last_received_bytes = self.received_bytes

    def on_dccmsg(self, connection, event):
        data = event.arguments[0]
        self.file.write(data.decode('utf-8') if self.args.stdout else data)
        self.received_bytes = self.received_bytes + len(data)
        self.dcc.send_bytes(struct.pack("!I", self.received_bytes))

        if not self.args.stdout:
            self.show_download_status()

    def on_dcc_disconnect(self, connection, event):
        if not self.args.stdout:
            self.file.close()
            print("")

        self.connection.quit()

    def on_welcome(self, connection, event):
        if self.args.verbose:
            print("Welcome page of the server was reached successfully.")
            print("Sending command to the bot...")

        if self.args.action == "list":
            self.connection.privmsg(self.args.bot,"xdcc send list")
        elif self.args.action == "send":
            self.connection.privmsg(self.args.bot,"xdcc send %s" % self.args.pack)

    def on_nicknameinuse(self, c, e):
        print("Failed! Nickname '%s' already in use" % self.args.nickname)
        self.connection.quit()

    def on_privnotice(self, c, e):
        if self.args.verbose:
            print("PRIVNOTICE: %s" % e.arguments[0])

        source = str(e.source)
        if source.startswith(self.args.bot):
            print("A error occurred!")
            print("-%s- %s" % (source, e.arguments[0]))
            self.connection.quit()

    def on_disconnect(self, connection, event):
        sys.exit(0)

def random_nickname():
    choices = itertools.permutations("anonymous")
    choices = list(choices)
    return "".join(random.choice(choices))

parser = argparse.ArgumentParser()
parser.add_argument("--server","-s",type=str,help="server",default="irc.rizon.net")
parser.add_argument("--port","-p",type=int,help="port number",default=6667)
parser.add_argument("--stdout","-t",action='store_true',
                    help="when used with the 'list' action, print the file to the stdout")
parser.add_argument("--nickname",'-n',type=str,
                    help="nickname to be used. The default is a random permutation of 'anonymous'",
                    default=random_nickname())
parser.add_argument("--verbose",'-v',action='store_true',help="enable verbose mode")
parser.add_argument("bot",type=str,help="bot name")
parser.add_argument("action",choices=["list",'send'],help="action to take")
parser.add_argument("pack",nargs='?',type=str,help="pack number of file")
args = parser.parse_args()

if args.action == "list" and args.pack :
    parser.error("action 'list' don't require a pack number.")
elif args.action == "send" and args.pack == None:
    parser.error("action 'send' require a pack number.")
elif args.stdout  and args.action != "list":
    parser.error("--stdout can only be used with the 'list' action")

if args.verbose:
    print("NickName: %s" % args.nickname)

c = DCCcat(args)
def cute_exit(sig, frame):
    print("SIGINT received! Quitting...")
    c.connection.quit()

signal.signal(signal.SIGINT,cute_exit)

try:
    c.connect(args.server, args.port, args.nickname)
except irc.client.ServerConnectionError as x:
    print(x)
    print("Something bad has happened")
    sys.exit(1)

c.start()
