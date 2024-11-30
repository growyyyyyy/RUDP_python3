import random
from tests.BasicTest import BasicTest

"""
This test simulates duplicate packet delivery in SACK mode.
"""


class SackDuplicatePacketTest(BasicTest):
    def __init__(self, forwarder, input_file):
        super(SackDuplicatePacketTest, self).__init__(
            forwarder, input_file, sackMode=True)

    def handle_packet(self):
        for p in self.forwarder.in_queue:
            self.forwarder.out_queue.append(p)  # 正常发送
            if random.choice([True, False]):  # 50% 概率发送重复包
                self.forwarder.out_queue.append(p)

        # 清空 in_queue
        self.forwarder.in_queue = []
