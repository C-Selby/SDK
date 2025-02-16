#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2021, Myriota Pty Ltd, All Rights Reserved
# SPDX-License-Identifier: BSD-3-Clause-Attribution
#
# This file is licensed under the BSD with attribution  (the "License"); you
# may not use these files except in compliance with the License.
#
# You may obtain a copy of the License here:
# LICENSE-BSD-3-Clause-Attribution.txt and at
# https://spdx.org/licenses/BSD-3-Clause-Attribution.html
#
# See the License for the specific language governing permissions and
# limitations under the License.


from __future__ import print_function
import argparse
import binascii
import os
import shutil
import signal
import struct
import sys
import tempfile
import time

file_types = {
    1: "system image",
    2: "user application",
    3: "network information",
}

header_length = (
    16  # header_version(1), reserved(1), type(2), length(4), reserved(6), checksum(2)
)
header_version = 0


def _bytecrc(crc, poly, n):
    mask = 1 << (n - 1)
    for i in range(8):
        if crc & mask:
            crc = (crc << 1) ^ poly
        else:
            crc = crc << 1
    mask = (1 << n) - 1
    crc = crc & mask
    return crc


def calc_crc(data):
    poly = 0x11021
    bit_size = 16
    table = [_bytecrc(i << (bit_size - 8), poly, bit_size) for i in range(256)]
    crc = 0
    for b in data:
        crc = table[b ^ ((crc >> 8) & 0xFF)] ^ ((crc << 8) & 0xFF00)
    return crc


def list_file(filename):
    try:
        print("List files from", filename, "\n")
        with open(filename, "rb") as input_file:
            totalsize = os.stat(filename).st_size
            if totalsize <= header_length:
                sys.stderr.write("File too small\n")
                sys.exit(1)

            offset = filenumber = 0
            while offset < totalsize:
                filenumber += 1
                print("------- File", filenumber, "-------")
                input_file.seek(2, os.SEEK_CUR)
                ftype = struct.unpack("<H", input_file.read(2))[0]
                if not ftype in file_types:
                    sys.stderr.write("File type error\n")
                    sys.exit(1)
                print("Type  :", file_types.get(ftype))

                flen = struct.unpack("<I", input_file.read(4))[0]
                print("Size  :", flen, "bytes", "\n")

                reserved = struct.unpack("<I", input_file.read(4))[0]
                reserved = struct.unpack("<H", input_file.read(2))[0]
                checksum = struct.unpack("<H", input_file.read(2))[0]

                input_file.seek(0 - header_length, os.SEEK_CUR)
                data = bytearray(input_file.read(header_length + flen))
                data[14] = data[15] = 0
                if checksum != (calc_crc(data) & 0xFFFF):
                    sys.stderr.write("Failed to verify file\n")
                    sys.exit(1)

                offset += header_length + flen

    except IOError:
        sys.stderr.write("\nCan't open %s\n" % filename)
        sys.exit(1)


def append_file(infile, outfile, type):
    got_failure = False
    try:
        with open(infile, "rb") as input_file:
            input_size = os.stat(infile).st_size
            try:
                outfile.seek(0, os.SEEK_END)
                outfile.write(struct.pack("<B", header_version))
                reserved = 0
                outfile.write(struct.pack("<B", reserved))
                outfile.write(struct.pack("<H", type))
                outfile.write(struct.pack("<I", input_size))
                outfile.write(struct.pack("<I", reserved))
                checksum = 0
                outfile.write(struct.pack("<H", reserved))
                outfile.write(struct.pack("<H", checksum))
                outfile.write(input_file.read(input_size))
                outfile.seek(0 - input_size - header_length, os.SEEK_CUR)
                data = bytearray(outfile.read(input_size + header_length))
                checksum = calc_crc(data) & 0xFFFF
                outfile.seek(14 - input_size - header_length, os.SEEK_CUR)
                outfile.write(struct.pack("<H", checksum))
            except IOError:
                sys.stderr.write("Failed to write to the output file\n")
                got_failure = True
                pass
    except IOError:
        sys.stderr.write("\nCan't open %s\n" % infile)
        got_failure = True
        pass

    if got_failure:
        sys.exit(1)
    else:
        input_file.close()


def signal_handler(signal, frame):
    sys.exit(0)


def main():
    signal.signal(signal.SIGINT, signal_handler)
    try:
        signal.signal(signal.SIGPIPE, signal_handler)
    except AttributeError:
        pass

    parser = argparse.ArgumentParser(
        description="Merge multiple files to program Myriota module",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-l",
        "--list_contents",
        dest="file_to_list",
        metavar="FILE",
        help="list contents in a merged file",
    )
    parser.add_argument(
        "-o",
        "--output",
        dest="merged_file",
        metavar="FILE",
        help="output of merge file",
    )
    parser.add_argument(
        "-f",
        "--system_file",
        dest="system_filename",
        metavar="FILE",
        help="system image binary file to be merged",
    )
    parser.add_argument(
        "-u",
        "--application_file",
        dest="application_filename",
        metavar="FILE",
        help="applicaiton binary file to be merged",
    )
    parser.add_argument(
        "-n",
        "--network_info_file",
        dest="network_info_filename",
        metavar="FILE",
        help="network information binary file to be merged",
    )

    args = parser.parse_args()

    if args.file_to_list:
        list_file(args.file_to_list)

    if args.system_filename or args.application_filename or args.network_info_filename:
        if not args.merged_file:
            sys.stderr.write("Please specify the output filename\n")
            sys.exit(1)
        output_temp = tempfile.NamedTemporaryFile(mode="w+b")
        output_temp_filename = output_temp.name
        if args.system_filename:
            append_file(args.system_filename, output_temp, 1)
        if args.application_filename:
            append_file(args.application_filename, output_temp, 2)
        if args.network_info_filename:
            append_file(args.network_info_filename, output_temp, 3)
        output_temp.flush()
        shutil.copyfile(output_temp_filename, args.merged_file)
        output_temp.close()


if __name__ == "__main__":
    main()
