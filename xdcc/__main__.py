"""A command line tool for downloading files from XDCC bots.

General Usage:
$ xdcc -s <server-name> -p <port-number> -c <channel>  botname [action] [packs]

For details on the available options use:
$ xdcc --help

Below are some examples using the default server and port number:

Print the list of available files to stdout:
$ xdcc --stdout 'YOUR-BOT-NAME-HERE' list

Download the files given by the pack numbers 500,501,502,503 and 510:
$ xdcc 'YOUR-BOT-NAME-HERE' send '500-503,510'

Same as above, but supposing that the bot requires you to be logged in a specific channel:
$ xdcc -c '#ChannelNameHere' 'YOUR-BOT-NAME-HERE' send '500-503,510'

"""
import sys
from time import time
import shlex
import os
import argparse
import itertools
import random
import signal
import logging

import irc.client

# Change the encoding to latin-1, since this will decode everything.
# For more information, consult the section Decoding Input in Jaraco Irc's documentation.
irc.client.ServerConnection.buffer_class.encoding = "latin-1"

def get_console_logger(name):
    """Return a logger that prints to the console.
    Args:
         name(str): The name of the logger

    Return:
         logging.getLogger: log
    """
    log = logging.getLogger(name)
    handler = logging.StreamHandler()
    handler.setLevel(logging.DEBUG)
    log.addHandler(handler)
    return log


LOG = get_console_logger("verbose")
ERASE_LINE = "\x1b[2K"


def hour_min_second(seconds):
    """Convert given numbers of seconds to the format hour:min:secs.
    Args:
        seconds(int): The number of seconds

    Return:
        str: a string on the format hours:mins:secs
    """
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return "%02d:%02d:%02d" % (hours, minutes, seconds)


def genpacks(packstr):
    """It is a generator that returns it pack number describe by some string on
    the format like '50-62,13,14,70-80'.

    Args:
        packstr(str): A string describing the range of packs
    Yields:
        int: The numeric pack of the next file to be downloaded.
    """
    l = packstr.split(",")
    for p in l:
        r = list(map(int, p.split("-")))
        try:
            s, e = r
        except ValueError:
            s = r[0]
            e = r[0]
        # raise error here
        for k in range(s, e + 1):
            yield k


class XDCC(irc.client.SimpleIRCClient):
    """This class implements a simple IRC client that connect to the specified server
    and channel(if any) to finally ask for a XDCC bot to send the requested file
    represented by the pack number passed on the command line options.

    Args:
        args(parser.args): The command-line arguments
    """

    def __init__(self, args):
        super().__init__()
        self.args = args
        self.packs_iter = genpacks(self.args.packs)

        self.received_bytes = 0
        self.total_size = 0
        self.last_received_bytes = 0
        self.last_print_time = 0

    def __getattr__(self, name):
        LOG.debug("An event has just triggered the non existent attribute %s!", name)
        msg = "{.__name__!r} object has no attribute {!r}"
        cls = type(self)
        raise AttributeError(msg.format(cls, name))

    def on_ctcp(self, connection, event):
        """Method called when a ctcp message has arrived.

        For more information on the connection and event arguments
        see the documentation for irc.client.SimpleIRCClient
        """
        LOG.debug("CTCP: %s", event.arguments)
        if event.arguments[0] != "DCC":
            return

        payload = event.arguments[1]
        parts = shlex.split(payload)
        command, filename, peer_address, peer_port, size = parts
        if command != "SEND":
            return

        self.filename = os.path.basename(filename)
        self.file = sys.stdout if self.args.stdout else open(self.filename, "wb")

        self.total_size = int(size)

        # Reset some important information
        self.received_bytes = 0
        self.last_received_bytes = 0
        self.last_print_time = 0

        peer_address = irc.client.ip_numstr_to_quad(peer_address)
        peer_port = int(peer_port)
        self.current_dcc_connection = self.dcc_connect(peer_address, peer_port, "raw")

    def show_download_status(self):
        """Show the download status interactively on the screen. Information such as
        filename, total transferred(in percentage), network speed and estimated time are
        currently shown.
        """
        now = time()
        if now - self.last_print_time >= 1:
            percentage = 100 * self.received_bytes / self.total_size
            speed = self.received_bytes - self.last_received_bytes
            erase_line_msg = "\r" + ERASE_LINE
            duration = hour_min_second((self.total_size - self.received_bytes) / speed)
            print(
                erase_line_msg
                + "%s: (%.2f%%) [%.2f MB/s] {%s}"
                % (self.filename, percentage, speed / (1e6), duration),
                end="",
            )
            sys.stdout.flush()

            self.last_print_time = now
            self.last_received_bytes = self.received_bytes

    def on_dccmsg(self, connection, event):
        """Receive a DCC msg block from the bot."""
        # Apparently the bots that i have used to test are both using the TURBO DCC instead
        # of the standard DCC.
        data = event.arguments[0]
        self.file.write(data.decode("utf-8") if self.args.stdout else data)
        self.received_bytes = self.received_bytes + len(data)

        # Since we are assuming a TURBO DCC transference, let close the connection when
        # the file has been completely transmitted.
        if self.received_bytes == self.total_size:
            self.current_dcc_connection.disconnect()

        if not self.args.stdout:
            self.show_download_status()

    def on_dcc_disconnect(self, connection, event):
        """This is called when the bot disconnect the DCC comunication."""
        LOG.debug("DCC connection closed by remote peer!")
        if not self.args.stdout:
            self.file.close()
            print("")

        if self.args.action == "send":
            try:
                self.request_file_to_bot()
            except StopIteration:
                self.connection.quit()
        else:  # list
            self.connection.quit()

    def request_file_to_bot(self):
        """Sends a ctcp message to the bot requesting the pack number specified
        on the command-line arguments.

        When the send action was chosen, this method raise StopIteration when there is
        no more pack to be downloaded.
        """
        LOG.debug("Sending command to the bot...")
        if self.args.action == "list":
            self.connection.ctcp("xdcc", self.args.bot, "send list")
        elif self.args.action == "send":
            self.connection.ctcp(
                "xdcc", self.args.bot, "send %d" % next(self.packs_iter)
            )

    def on_welcome(self, c, e):
        """This is called when we are welcomed by the IRC server."""
        LOG.debug("Welcome page of the server was reached successfully.")
        if self.args.channel:
            self.requested = False
            self.connection.join(self.args.channel)
        else:
            self.request_file_to_bot()

    def on_join(self, c, e):
        """Called when we successfully joined the channel."""
        # Some channels can trigger this function multiple times
        LOG.debug("Joined to channel %s.", self.args.channel)
        if not self.requested:
            self.request_file_to_bot()
            self.requested = True

    def on_nicknameinuse(self, c, e):
        """Called when our nickname are already in use. It should be a rare
        event."""
        print("Failed! Nickname '%s' already in use" % self.args.nickname)
        self.connection.quit()

    def on_privnotice(self, c, e):
        """Called when someone(server, channel or bot) sends a privnotice for
        us."""
        LOG.debug("PRIVNOTICE: %s", e.arguments[0])

        source = str(e.source)
        if source.startswith(self.args.bot):
            print("-%s- %s" % (source, e.arguments[0]))

    def on_disconnect(self, connection, event):
        """Called when disconnecting from the server."""
        LOG.debug("Disconnected!")
        sys.exit(0)


def random_nickname():
    """Return a randomly chosen anagram of the word anonymous."""
    choices = itertools.permutations("anonymous")
    choices = list(choices)
    return "".join(random.choice(choices))


def main():
    """Our main function."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--server",
        "-s",
        type=str,
        help="The server to connect. The default is irc.rizon.net.",
        default="irc.rizon.net",
    )
    parser.add_argument(
        "--channel",
        "-c",
        type=str,
        help="The channel to join. The default is to not join in any server.",
    )
    parser.add_argument(
        "--port",
        "-p",
        type=int,
        help="The port number of the server. The default is 6670.",
        default=6670,
    )
    parser.add_argument(
        "--stdout",
        "-t",
        action="store_true",
        help="When used with the 'list' action, print the contents of the list file to the stdout.",
    )
    parser.add_argument(
        "--nickname",
        "-n",
        type=str,
        help="Nickname to be used in the server. If this option is not provided,"
        " a random permutation of 'anonymous' will be used.",
        default=random_nickname(),
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose mode."
    )
    parser.add_argument("bot", type=str, help="The XDCC Bot name.")
    parser.add_argument(
        "action",
        choices=["list", "send"],
        help="Action to take. Use 'list' for get the file list from the bot. "
        "Use 'send' to get a file from the bot.",
    )
    parser.add_argument(
        "packs",
        nargs="?",
        type=str,
        help="Packs numbers of the desired files. Ex: '50-62,64,66,70-80'.",
    )
    args = parser.parse_args()

    if args.action == "list" and args.packs:
        parser.error("action 'list' don't require a pack number.")
    elif args.action == "send" and args.packs is None:
        parser.error("action 'send' require a pack number.")
    elif args.stdout and args.action != "list":
        parser.error("--stdout can only be used with the 'list' action")

    if args.verbose:
        LOG.setLevel(logging.DEBUG)

    LOG.debug("Using nickname %s", args.nickname)

    c = XDCC(args)

    def cute_exit(sig, frame):
        """Try to disconnect from the server when a SIGINT is received."""
        print("SIGINT received! Quitting...")
        c.connection.quit()

    signal.signal(signal.SIGINT, cute_exit)

    try:
        c.connect(args.server, args.port, args.nickname)
    except irc.client.ServerConnectionError as x:
        print(x)
        print("Something bad has happened")
        sys.exit(1)

    c.start()


if __name__ == "__main__":
    main()
