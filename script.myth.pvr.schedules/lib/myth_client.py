# encoding=utf-8
#                Copyright 2015 - 2020 Steven Carreck
#                    GNU GENERAL PUBLIC LICENSE
#                       Version 3, 29 June 2007
#     This file is part of Myth PVR Schedules.
#     This program is free software: you can redistribute it and/or modify
#     it under the terms of the GNU General Public License as published by
#     the Free Software Foundation, either version 3 of the License, or
#     (at your option) any later version.
#
#     This program is distributed in the hope that it will be useful,
#     but WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#     GNU General Public License for more details.
#
#     You should have received a copy of the GNU General Public License
#     along with this program.  If not, see <http://www.gnu.org/licenses/>.

__author__ = 'Steven Carreck'

import socket
import select
import xbmc  # For logging.

class MythClient:
    def __init__(self, myth_server_host, myth_server_port, myth_protocol_version, block_shutdown=False,
                 debug_mode=False):
        self.debug_mode = debug_mode
        self.__myth_server_host = myth_server_host
        self.__myth_server_port = myth_server_port
        self.__protocol_version = self.__set_protocol_string(myth_protocol_version)
        self.__subscribe_str = self.__set_subscribe_string()
        self.__block_shutdown = block_shutdown
        self.__connection_phase = ''
        self.__proto_accepted = False
        self.__subscription_sent = False
        self.__subscribed = False
        self.__sock_in = []
        self.__sock_out = []
        self.__sock_excpt = []
        self.sock_err = False
        self.socket_timeout = 4.0

    def __call__(self):
        if self.debug_mode:
            self.debug_log('connect_myth_client')
        # Try connect to the Myth Server.
        self.__sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.__sock.settimeout(self.socket_timeout)
        self.__connection_phase = 'socket Connect'
        self.notify('TRY_CONNECT')
        try_connect = self.__sock.connect_ex((self.__myth_server_host, int(self.__myth_server_port)))
        if try_connect == 0:
            self.__connection_phase = 'Send Proto'
            self.__send_data(self.__protocol_version)
            while True:
                # Monitor socket changes and wait at select.
                if self.debug_mode:
                    self.debug_log('select wait')
                self.__sock_in, self.__sock_out, self.__sock_excpt = \
                    select.select([self.__sock], [], [], None)

                if not self.sock_err:
                    try:
                        if len(self.__sock_in) > 0:
                            data = self.__sock_in[0].recv(128)
                            # print 'Reply:' + data
                            if data == "":
                                self.notify('SOCK_CLOSE')
                                if self.debug_mode:
                                    self.debug_log('SOCK_CLOSE - Sock recv')
                                break
                            else:
                                # Interpret received data.
                                self.__interpret(data)

                    except socket.error, err:
                        self.__sock.shutdown(socket.SHUT_RDWR)
                        self.__sock.close()
                        self.notify('SOCK_CLOSE')
                        if self.debug_mode:
                            self.debug_log('SOCK_CLOSE - sock error')
                        break
        else:
            self.__sock = None
            self.notify('CONNECTION_TIMEOUT')
            if self.debug_mode:
                self.debug_log('CONNECTION_TIMEOUT')

    def __interpret(self, reply):
        """ Manage subscription steps and notify of server schedule change events."""
        if self.debug_mode:
            self.debug_log('__interpret')
        # Check Myth Protocol accepted.
        if self.__connection_phase == 'Send Proto':
            if reply.find('ACCEPT') > 0:
                self.__proto_accepted = True
                self.notify('PROTO_ACCEPT')
                if self.debug_mode:
                    self.debug_log('PROTO_ACCEPT')
                # Subscribe to the server events as monitor.
                self.__connection_phase = 'Subscribe'
                self.__send_data(self.__subscribe_str)
                self.__subscription_sent = True

        if reply.find('REJECT') > 0:
            # Server will close socket on rejection.
            self.notify('PROTO_REJECT')
            if self.debug_mode:
                self.debug_log('PROTO_REJECT')

        # Check Subscription OK, and we are the client being accepted..
        if self.__connection_phase == 'Subscribe':
            if reply.find('CLIENT_CONNECTED') > 0 and reply.find(socket.gethostname().upper()) \
                    or reply.find('OK') > 0:
                self.__connection_phase = 'Monitor Rec Updates'
                self.__subscribed = True
                self.notify('CLIENT_CONNECTED')
                if self.debug_mode:
                    self.debug_log('CLIENT_CONNECTED')
                if self.__block_shutdown:
                    self.__send_data('14      BLOCK_SHUTDOWN')

        # Notify if recording schedules changed.
        if self.__connection_phase == 'Monitor Rec Updates':
            if reply.find('SCHEDULE_CHANGE') > 0:
                self.notify('SCHEDULE_CHANGE')
                if self.debug_mode:
                    self.debug_log('SCHEDULE_CHANGE')

        if reply.find('MASTER_SHUTDOWN') > 0:
            self.notify('MASTER_SHUTDOWN')
            if self.debug_mode:
                self.debug_log('MASTER_SHUTDOWN')

    def __send_data(self, data):
        if self.debug_mode:
            self.debug_log('__send_data')
        if not self.sock_err:
            try:
                self.__sock.sendall(data)

            except socket.error, err:
                if self.debug_mode:
                    self.debug_log('__send_data - socket error')
                self.sock_err = True
                self.__sock.shutdown(socket.SHUT_RDWR)
                self.__sock.close()
                self.notify('SOCK_CLOSE')
                if self.debug_mode:
                    self.debug_log('__send_data - SOCK_CLOSE')

    def notify(self, message):
        """ Override me. Myth server connection status & events."""
        pass

    def __set_protocol_string(self, myth_proto_ver):
        """ Format protocol handshake."""
        string_length = str(len("MYTH_PROTO_VERSION " + myth_proto_ver))
        protocol_version = string_length.ljust(8) + "MYTH_PROTO_VERSION " + myth_proto_ver
        if self.debug_mode:
            self.debug_log('__set_protocol_string - ' + protocol_version)
        return protocol_version

    def __set_subscribe_string(self):
        """ Format subscription command."""
        host_name = socket.gethostname()
        string_length = str(len("ANN Monitor " + host_name + " 1"))
        subscribe_string = string_length.ljust(8) + "ANN Monitor " + host_name + " 1"
        if self.debug_mode:
            self.debug_log('__set_subscribe_string - ' + subscribe_string)
        return subscribe_string

    def disconnect(self):
        if self.debug_mode:
            self.debug_log('disconnect')
        if self.__subscribed and not self.sock_err:
            if self.__block_shutdown:
                self.__send_data('14      ALLOW_SHUTDOWN')
                if self.debug_mode:
                    self.debug_log('ALLOW_SHUTDOWN')
            # Sending DONE will cause the Myth server to close the socket.
            self.__send_data('4       DONE')
            if self.debug_mode:
                    self.debug_log('DONE')

    def debug_log(self, message, log_level=xbmc.LOGNOTICE):
        """ Logs debug info to disk."""
        # Debug - $HOME/.kodi/temp/kodi.log, %APPDATA%\Kodi\kodi.log, special://logpath (this can be used by scripts)
        prefix = 'Myth PVR Schedules - myth_client.py: '
        xbmc.log(msg=prefix + message, level=log_level)

