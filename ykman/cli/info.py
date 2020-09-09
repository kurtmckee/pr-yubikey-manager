# Copyright (c) 2016 Yubico AB
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

from __future__ import absolute_import

from yubikit.core import INTERFACE
from yubikit.core.iso7816 import ApduError
from yubikit.otp import YkCfgApplication
from yubikit.oath import OathApplication

from ..hid import list_devices as list_hid
from ..scard import list_devices as list_ccid

from ..otp import OtpController
from ..oath import is_in_fips_mode as oath_in_fips_mode
from ..fido import FIPS_U2F_CMD
from ..device import is_fips_version, get_name, read_info
from ..util import APPLICATION, TRANSPORT

import click
import logging


logger = logging.getLogger(__name__)


def print_app_status_table(supported_apps, enabled_apps):
    usb_supported = supported_apps.get(INTERFACE.USB, 0)
    usb_enabled = enabled_apps.get(INTERFACE.USB, 0)
    nfc_supported = supported_apps.get(INTERFACE.NFC, 0)
    nfc_enabled = enabled_apps.get(INTERFACE.NFC, 0)
    rows = []
    for app in APPLICATION:
        if app & usb_supported:
            if app & usb_enabled:
                usb_status = "Enabled"
            else:
                usb_status = "Disabled"
        else:
            usb_status = "Not available"
        if nfc_supported:
            if app & nfc_supported:
                if app & nfc_enabled:
                    nfc_status = "Enabled"
                else:
                    nfc_status = "Disabled"
            else:
                nfc_status = "Not available"
            rows.append([str(app), usb_status, nfc_status])
        else:
            rows.append([str(app), usb_status])

    column_l = []
    for row in rows:
        for idx, c in enumerate(row):
            if len(column_l) > idx:
                if len(c) > column_l[idx]:
                    column_l[idx] = len(c)
            else:
                column_l.append(len(c))

    f_apps = "Applications".ljust(column_l[0])
    if nfc_supported:
        f_USB = "USB".ljust(column_l[1])
        f_NFC = "NFC".ljust(column_l[2])
    f_table = ""

    for row in rows:
        for idx, c in enumerate(row):
            f_table += "{}\t".format(c.ljust(column_l[idx]))
        f_table += "\n"

    if nfc_supported:
        click.echo("{}\t{}\t{}".format(f_apps, f_USB, f_NFC))
    else:
        click.echo("{}".format(f_apps))
    click.echo(f_table, nl=False)


def get_overall_fips_status(pid, info):
    statuses = {}

    usb_enabled = info.config.enabled_applications[INTERFACE.USB]

    hid_devices = list_hid()

    statuses["OTP"] = False
    if usb_enabled & APPLICATION.OTP:
        for dev in hid_devices:
            if dev.pid == pid and dev.has_otp:
                with dev.open_otp_connection() as conn:
                    app = YkCfgApplication(conn)
                    if app.get_serial() == info.serial:
                        statuses["OTP"] = OtpController(app).is_in_fips_mode
                        break

    statuses["OATH"] = False
    if usb_enabled & APPLICATION.OATH:
        for dev in list_ccid():
            with dev.open_iso7816_connection() as conn:
                info2 = read_info(pid, conn)
                if info2.serial == info.serial:
                    app = OathApplication(conn)
                    statuses["OATH"] = oath_in_fips_mode(app)
                    break

    statuses["FIDO U2F"] = False
    if usb_enabled & APPLICATION.U2F:
        for dev in hid_devices:
            if dev.pid == pid and dev.has_ctap:
                with dev.open_ctap_device() as ctap:
                    info2 = read_info(pid, ctap)
                    if info2.serial == info.serial:
                        try:
                            ctap.send_apdu(ins=FIPS_U2F_CMD.VERIFY_FIPS_MODE)
                            statuses["FIDO U2F"] = True
                        except ApduError:
                            pass
                        break

    return statuses


def check_fips_status(pid, info):
    if is_fips_version(info.version):
        fips_status = get_overall_fips_status(pid, info)
        click.echo()

        click.echo(
            "FIPS Approved Mode: {}".format(
                "Yes" if all(fips_status.values()) else "No"
            )
        )

        status_keys = list(fips_status.keys())
        status_keys.sort()
        for status_key in status_keys:
            click.echo(
                "  {}: {}".format(
                    status_key, "Yes" if fips_status[status_key] else "No"
                )
            )


@click.option(
    "-c",
    "--check-fips",
    help="Check if YubiKey is in FIPS Approved mode.",
    is_flag=True,
)
@click.command()
@click.pass_context
def info(ctx, check_fips):
    """
    Show general information.

    Displays information about the attached YubiKey such as serial number,
    firmware version, applications, etc.
    """
    pid = ctx.obj["pid"]
    key_type = pid.get_type()
    transports = pid.get_transports()
    info = ctx.obj["info"]

    device_name = get_name(key_type, info)

    click.echo("Device type: {}".format(device_name))
    click.echo("Serial number: {}".format(info.serial or "Not set or unreadable"))
    if info.version:
        f_version = ".".join(str(x) for x in info.version)
        click.echo("Firmware version: {}".format(f_version))
    else:
        click.echo(
            "Firmware version: Uncertain, re-run with only one " "YubiKey connected"
        )

    if info.form_factor:
        click.echo("Form factor: {!s}".format(info.form_factor))
    click.echo("Enabled USB interfaces: {}".format(TRANSPORT.split(transports)))
    if INTERFACE.NFC in info.supported_applications:
        f_nfc = (
            "enabled"
            if info.config.enabled_applications.get(INTERFACE.NFC)
            else "disabled"
        )
        click.echo("NFC interface is {}.".format(f_nfc))
    if info.is_locked:
        click.echo("Configured applications are protected by a lock code.")
    click.echo()

    print_app_status_table(
        info.supported_applications, info.config.enabled_applications
    )

    if check_fips:
        ctx.obj["conn"].close()
        check_fips_status(pid, info)
