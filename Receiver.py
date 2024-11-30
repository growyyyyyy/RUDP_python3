import socket
import getopt
import sys
import time
import Checksum


class Connection():
    def __init__(self, host, port, start_seq, debug=False):
        self.debug = debug
        self.updated = time.time()
        self.current_seqno = start_seq - 1  # expect to ack from the start_seqno
        self.host = host
        self.port = port
        self.max_buf_size = 5
        self.outfile = open(f"{host}.{port}", "wb")
        self.seqnums = {}  # enforce single instance of each seqno

    def ack(self, seqno, data, sackMode=False):
        res_data = []
        sacks = []
        self.updated = time.time()

        # 将数据按序存储并返回
        if seqno > self.current_seqno and seqno <= self.current_seqno + self.max_buf_size:
            self.seqnums[seqno] = bytes.fromhex(data)  # 将十六进制数据转换为原始二进制
            for n in sorted(self.seqnums.keys()):
                if n == self.current_seqno + 1:
                    self.current_seqno += 1
                    res_data.append(self.seqnums[n])
                    del self.seqnums[n]
                else:
                    break  # 当发现不连续的序号时，退出循环

        if self.debug:
            print(
                f"Receiver.py: next seqno should be {self.current_seqno + 1}")

        # 生成累积确认和选择性确认
        if sackMode:
            for n in sorted(self.seqnums.keys()):
                sacks.append(n)
            return f"{self.current_seqno + 1};{','.join(map(str, sacks))}", res_data
        else:
            return str(self.current_seqno + 1), res_data

    def record(self, data):
        self.outfile.write(data)
        self.outfile.flush()

    def end(self):
        self.outfile.close()


class Receiver():
    def __init__(self, listenport=33122, debug=False, timeout=10, sackMode=False):
        self.debug = debug
        self.timeout = timeout
        self.sackMode = sackMode
        self.last_cleanup = time.time()
        self.port = listenport
        self.host = ''
        self.s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.s.settimeout(timeout)
        self.s.bind((self.host, self.port))
        self.connections = {}  # schema is {(address, port): Connection}
        self.MESSAGE_HANDLER = {
            'start': self._handle_start,
            'data': self._handle_data,
            'end': self._handle_end,
            'ack': self._handle_ack
        }

    def start(self):
        while True:
            try:
                message, address = self.receive()
                message = message.decode()
                msg_type, seqno, data, checksum = self._split_message(message)
                try:
                    seqno = int(seqno)
                except ValueError:
                    raise ValueError("Invalid sequence number in message.")
                if self.debug:
                    print(
                        f"Receiver.py: received {msg_type}|{seqno}|{data[:5]}|{checksum}")

                if Checksum.validate_checksum(message):
                    self.MESSAGE_HANDLER.get(
                        msg_type, self._handle_other)(seqno, data, address)
                elif self.debug:
                    print(
                        f"Receiver.py: checksum failed: {msg_type}|{seqno}|{data[:5]}|{checksum}")

                if time.time() - self.last_cleanup > self.timeout:
                    self._cleanup()
            except socket.timeout:
                self._cleanup()
            except (KeyboardInterrupt, SystemExit):
                exit()
            except ValueError as e:
                if self.debug:
                    print(f"Receiver.py: {e}")
                pass  # ignore invalid packets

    def receive(self):
        return self.s.recvfrom(4096)

    def send(self, message, address):
        self.s.sendto(message.encode(), address)

    def _send_ack(self, seqno, address):
        if self.sackMode:
            m = f"sack|{seqno}|"
        else:
            m = f"ack|{seqno}|"
        checksum = Checksum.generate_checksum(m)
        message = f"{m}{checksum}"
        if self.debug:
            print(f"Receiver.py: send ack {message}")
        self.send(message, address)

    def _handle_start(self, seqno, data, address):
        if address not in self.connections:
            self.connections[address] = Connection(
                address[0], address[1], seqno, self.debug)
        conn = self.connections[address]
        ackno, res_data = conn.ack(seqno, data, self.sackMode)
        for chunk in res_data:
            conn.record(chunk)
        self._send_ack(ackno, address)

    def _handle_data(self, seqno, data, address):
        if address in self.connections:
            conn = self.connections[address]
            ackno, res_data = conn.ack(seqno, data, self.sackMode)
            for chunk in res_data:
                conn.record(chunk)
            self._send_ack(ackno, address)

    def _handle_end(self, seqno, data, address):
        if address in self.connections:
            conn = self.connections[address]
            ackno, res_data = conn.ack(seqno, data, self.sackMode)
            for chunk in res_data:
                conn.record(chunk)
            self._send_ack(ackno, address)

    def _handle_ack(self, seqno, data, address):
        pass  # ACKs are not relevant to the receiver itself

    def _handle_other(self, seqno, data, address):
        pass  # Unrecognized messages are ignored

    def _split_message(self, message):
        pieces = message.split('|')
        msg_type, seqno = pieces[0:2]
        checksum = pieces[-1]
        data = '|'.join(pieces[2:-1])
        return msg_type, seqno, data, checksum

    def _cleanup(self):
        if self.debug:
            print("Receiver.py: clean up time")
        now = time.time()
        for address in list(self.connections.keys()):
            conn = self.connections[address]
            if now - conn.updated > self.timeout:
                if self.debug:
                    print(
                        f"Receiver.py: killed connection to {address} ({now - conn.updated:.2f} old)")
                conn.end()
                del self.connections[address]
        self.last_cleanup = now


if __name__ == "__main__":
    def usage():
        print("RUDP Receiver")
        print("-p PORT | --port=PORT The listen port, defaults to 33122")
        print("-t TIMEOUT | --timeout=TIMEOUT Receiver timeout in seconds")
        print("-d | --debug Print debug messages")
        print("-h | --help Print this usage message")
        print("-k | --sack Enable selective acknowledgement mode")

    try:
        opts, args = getopt.getopt(sys.argv[1:], "p:dt:k", [
                                   "port=", "debug=", "timeout=", "sack="])
    except:
        usage()
        exit()

    port = 33122
    debug = False
    timeout = 10
    sackMode = False

    for o, a in opts:
        if o in ("-p", "--port="):
            port = int(a)
        elif o in ("-t", "--timeout="):
            timeout = int(a)
        elif o in ("-d", "--debug="):
            debug = True
        elif o in ("-k", "--sack="):
            sackMode = True
        else:
            usage()
            exit()

    r = Receiver(port, debug, timeout, sackMode)
    r.start()
