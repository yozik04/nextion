command_failed_codes = {
    0x00: "Invalid Instruction",
    0x02: "Invalid Component ID",
    0x03: "Invalid Page ID",
    0x04: "Invalid Picture ID",
    0x05: "Invalid Font ID",
    0x06: "Invalid File Operation",
    0x09: "Invalid CRC",
    0x11: "Invalid Baud rate Setting",
    0x12: "Invalid Waveform ID or Channel #",
    0x1A: "Invalid Variable name or attribute",
    0x1B: "Invalid Variable Operation",
    0x1C: "Assignment failed to assign",
    0x1D: "EEPROM Operation failed",
    0x1E: "Invalid Quantity of Parameters",
    0x1F: "IO Operation failed",
    0x20: "Escape Character Invalid",
    0x23: "Variable name too long",
    0x24: "Serial Buffer Overflow",
}


class NextionException(Exception):
    pass


class CommandFailed(NextionException):
    def __init__(self, command, code):
        if code in command_failed_codes:
            msg = f"{command_failed_codes[code]} for command: {command}"
        else:
            msg = "Unknown response code 0x{:02x} for command: '{}'".format(
                code, command
            )

        super().__init__(msg)


class CommandTimeout(NextionException):
    pass


class ConnectionFailed(NextionException):
    pass


class UnsupportedBaudRate(ConnectionFailed):
    pass


class NoValidReply(ConnectionFailed):
    pass


class InvalidReply(ConnectionFailed):
    pass
