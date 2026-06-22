import rclpy
from rclpy.node import Node
from rclpy.logging import LoggingSeverity
from std_msgs.msg import String
import json



class TestChangeMap(Node):
    def __init__(self):
        super().__init__('test_change_map')

        self.declare_parameter('loglevel', "info")
        loglevel = self.get_parameter('loglevel').value
        if loglevel == "debug":
            self._logger.set_level(LoggingSeverity.DEBUG)
        else:
            self._logger.set_level(LoggingSeverity.INFO)

        # マップ変更コマンドパブリッシャー
        self.publisher_ = self.create_publisher(String,'/client_api/robotMapChange',1)

        # テストコマンド1回送信
        self.send_test_change_map()
        


    def send_test_change_map(self):
        test_json = {
            "map": "buildingB"
        }
        self.get_logger().info('Sending test change map command: "%s"' % str(test_json))
        msg = String()
        msg.data = json.dumps(test_json)
        self.publisher_.publish(msg)
        self.get_logger().info('Test change map command sent.')


def main(args=None):
    print('Hi from test_change_map.')

    rclpy.init(args=args)

    node = TestChangeMap()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()