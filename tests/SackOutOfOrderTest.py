import random
from tests.BasicTest import BasicTest

"""
This test simulates out-of-order packet delivery in SACK mode.
"""


class SackOutOfOrderTest(BasicTest):
    def __init__(self, forwarder, input_file):
        super(SackOutOfOrderTest, self).__init__(
            forwarder, input_file, sackMode=True)

    def handle_packet(self):
        delayed_packets = []
        for p in self.forwarder.in_queue:
            if random.choice([True, False]):  # 50% 概率延迟发送
                delayed_packets.append(p)
            else:
                self.forwarder.out_queue.append(p)  # 正常发送

        # 以随机顺序插入延迟的包
        while delayed_packets:
            self.forwarder.out_queue.append(delayed_packets.pop(
                random.randint(0, len(delayed_packets) - 1)))

        # 清空 in_queue
        self.forwarder.in_queue = []
