# Copyright (c) 2015 Yubico AB
# All rights reserved.
#
#   Redistribution and use in source and binary forms, with or
#   without modification, are permitted provided that the following
#   conditions are met:
#
#    1. Redistributions of source code must retain the above copyright
#       notice, this list of conditions and the following disclaimer.
#    2. Redistributions in binary form must reproduce the above
#       copyright notice, this list of conditions and the following
#       disclaimer in the documentation and/or other materials provided
#       with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
# FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
# COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
# ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.


from smartcard import System
from .driver import AbstractDriver
from .util import Mode, CAPABILITY

OTP_AID = '\xa0\x00\x00\x05\x27\x20\x01'
MGR_AID = '\xa0\x00\x00\x05\x27\x47\x11\x17'

KNOWN_APPLETS = {
    OTP_AID: CAPABILITY.OTP,
    '\xa0\x00\x00\x06\x47\x2f\x00\x01': CAPABILITY.U2F,  # Official
    '\xa0\x00\x00\x05\x27\x10\x02': CAPABILITY.U2F,  # Yubico - No longer used
    '\xa0\x00\x00\x03\x08': CAPABILITY.PIV,
    '\xd2\x76\x00\x01\x24\x01': CAPABILITY.OPGP,
    '\xa0\x00\x00\x05\x27\x21\x01': CAPABILITY.OATH
}


class CCIDDriver(AbstractDriver):
    """
    Pyscard based CCID driver
    """
    transport = 'CCID'

    def __init__(self, connection, name=''):
        self._conn = connection
        self._mode = Mode(
            otp='OTP' in name,
            u2f='U2F' in name,
            ccid='CCID' in name
        )
        if ' NEO ' in name:  # At least 3.0.0
            self._version = (3, 0, 0)
        elif ' 4 ' in name:  # At least 4.1.0 if CCID is available.
            self._version = (4, 1, 0)
        self._read_version()  # Overwrite with exact version, if possible.

    def _read_version(self):
        s, sw = self.send_apdu(0, 0xa4, 4, 0, OTP_AID)
        if sw == 0x9000:
            self._version = tuple(map(ord, s[:3]))

    def read_capabilities(self):
        if self.version == (4, 2, 4):  # 4.2.4 doesn't report capa correctly.
            return '\x03\x01\x01\x3f'
        _, sw = self.send_apdu(0, 0xa4, 4, 0, MGR_AID)
        if sw != 0x9000:
            return ''
        capa, sw = self.send_apdu(0, 0x1d, 0, 0)
        return capa

    def probe_applet_support(self):
        capa = 0
        for aid, code in KNOWN_APPLETS.items():
            _, sw = self.send_apdu(0, 0xa4, 4, 0, aid)
            if sw == 0x9000:
                capa |= code
        return capa

    def send_apdu(self, cl, ins, p1, p2, data=''):
        header = [cl, ins, p1, p2, len(data)]
        resp, sw1, sw2 = self._conn.transmit(header + map(ord, data))
        return ''.join(map(chr, resp)), sw1 << 8 | sw2

    def __del__(self):
        self._conn.disconnect()


def open_device():
    for reader in System.readers():
        if reader.name.lower().startswith('yubico yubikey'):
            conn = reader.createConnection()
            conn.connect()
            return CCIDDriver(conn, reader.name)
