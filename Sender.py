import socket
import getopt
import sys
import Checksum
import BasicSender
from tqdm import tqdm  # 导入 tqdm 进度条库


class Sender(BasicSender.BasicSender):
    def __init__(self, dest, port, filename, debug=False, sackMode=False):
        super(Sender, self).__init__(dest, port, filename, debug)
        self.sackMode = sackMode
        self.window_size = 5  # 窗口大小
        self.base = 0  # 窗口起始序号
        self.next_seqno = 0  # 下一个待发送的包序号
        self.packets = []  # 需要发送的所有数据包
        self.acks = []  # 用于记录确认状态的列表
        self.timeout_interval = 0.5  # 超时时间

    def start(self):
        """
        主发送逻辑
        """
        self.create_packets()

        # 初始化进度条
        with tqdm(total=len(self.packets), desc="Sending", unit="pkt") as pbar:
            while self.base < len(self.packets):
                self.send_window()
                try:
                    response = self.receive(timeout=self.timeout_interval)
                    if response:
                        self.handle_response(response.decode())
                except socket.timeout:
                    self.handle_timeout()

                # 更新进度条
                pbar.n = self.base  # 更新当前已确认的包数
                pbar.refresh()

    def create_packets(self):
        """
        将文件读取并分割为 RUDP 数据包
        """
        seqno = 0
        with open(self.infile.name, "rb") as f:
            while True:
                data = f.read(500)  # 按 500 字节分割文件
                if not data:
                    break

                msg_type = "data"
                if seqno == 0:
                    msg_type = "start"
                elif len(data) < 500:
                    msg_type = "end"

                # 直接将二进制数据转为字符串
                packet = self.make_packet(msg_type, seqno, data.hex())
                self.packets.append(packet)
                seqno += 1

        self.acks = [False] * len(self.packets)

    def send_window(self):
        """
        在当前窗口内发送未确认的数据包
        """
        for seqno in range(self.base, min(self.base + self.window_size, len(self.packets))):
            if not self.acks[seqno]:
                self.send(self.packets[seqno])
                self.log(f"Sent packet: {self.packets[seqno]}")

    def handle_response(self, response_packet):
        """
        处理接收端返回的 ACK 或 SACK 响应
        """
        if not Checksum.validate_checksum(response_packet):
            self.log(f"Invalid checksum for response: {response_packet}")
            return

        parts = response_packet.split('|')
        ack_type = parts[0]
        if ack_type == "ack":
            ack_seqno = int(parts[1])
            self.handle_ack(ack_seqno)
        elif ack_type == "sack" and self.sackMode:
            sack_info = parts[1].split(';')
            cumulative_ack = int(sack_info[0])
            selective_acks = [int(x) for x in sack_info[1].split(',') if x]
            self.handle_ack(cumulative_ack)
            for seqno in selective_acks:
                self.acks[seqno] = True

    def handle_ack(self, ack_seqno):
        """
        处理累积确认，更新窗口起始序号
        """
        if ack_seqno > self.base:
            for i in range(self.base, ack_seqno):
                self.acks[i] = True
            self.base = ack_seqno
        self.log(f"New base: {self.base}")

    def handle_timeout(self):
        """
        超时处理，重新发送窗口内的未确认数据包
        """
        self.log("Timeout occurred, resending window")
        self.send_window()

    def log(self, msg):
        """
        打印调试信息
        """
        if self.debug:
            print(msg)


if __name__ == "__main__":
    def usage():
        print("RUDP Sender")
        print("-f FILE | --file=FILE The file to transfer; if empty reads from STDIN")
        print("-p PORT | --port=PORT The destination port, defaults to 33122")
        print("-a ADDRESS | --address=ADDRESS The receiver address or hostname, defaults to localhost")
        print("-d | --debug Print debug messages")
        print("-h | --help Print this usage message")
        print("-k | --sack Enable selective acknowledgement mode")

    try:
        opts, args = getopt.getopt(
            sys.argv[1:], "f:p:a:dk", [
                "file=", "port=", "address=", "debug", "sack"]
        )
    except getopt.GetoptError:
        usage()
        sys.exit(2)

    port = 33122
    dest = "localhost"
    filename = None
    debug = False
    sackMode = False

    for o, a in opts:
        if o in ("-f", "--file"):
            filename = a
        elif o in ("-p", "--port"):
            port = int(a)
        elif o in ("-a", "--address"):
            dest = a
        elif o in ("-d", "--debug"):
            debug = True
        elif o in ("-k", "--sack"):
            sackMode = True

    sender = Sender(dest, port, filename, debug, sackMode)
    try:
        sender.start()
    except KeyboardInterrupt:
        sys.exit()
