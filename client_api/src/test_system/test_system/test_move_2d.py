#!/usr/bin/env python3

import rclpy #ROS2 を Python で開発する場合必須
from rclpy.node import Node #Nodeでやり取りするのに使う？
from rclpy.logging import LoggingSeverity
from std_msgs.msg import String #Json(String)をいつも使うので
from geometry_msgs.msg import PoseStamped
import json



class TestMove2D(Node):
    def __init__(self):
        super().__init__('test_move_2d')

        self.declare_parameter('loglevel', "info")
        loglevel = self.get_parameter('loglevel').value
        if loglevel == "debug":
            self._logger.set_level(LoggingSeverity.DEBUG) #logの出力レベル
        else:
            self._logger.set_level(LoggingSeverity.INFO) #logの出力レベル

        # 2D移動コマンド送信
        self.publisher_ = self.create_publisher(String,'/client_api/goal_2d',1)

        # テストコマンド1回送信
        self.send_test_move_2d()
        


    def send_test_move_2d(self):
        test_json = {
            "ID" : {
                "robot_name": "robotA",
                "UUID": "123e4567-e89b-12d3-a456-426614174000",
                "type": 0
            },
            "move_order": [
                {
                    "serial_number":0,
                    "x" : 40.72196960449219,
                    "y" : 4.704837799072266,
                    "z" : 0.00,
                    "t" : 163.40658675886525,
                }
            ]
        }
        self.get_logger().info('Sending test 2D Move command: "%s"' % str(test_json))
        msg = String()
        msg.data = json.dumps(test_json)
        self.publisher_.publish(msg)
        self.get_logger().info('Test 2D Move command sent.')








def main(args=None):
    print('Hi from test_move_2d.')

    rclpy.init(args=args)   #初期化　絶対書く

    node = TestMove2D()
    rclpy.spin(node)  # 終了まで待機
    node.destroy_node() #ノードの破壊
    rclpy.shutdown() # 終了処理

if __name__ == '__main__':
    main()
