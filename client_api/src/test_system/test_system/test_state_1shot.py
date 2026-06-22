#!/usr/bin/env python3

import rclpy #ROS2 を Python で開発する場合必須
from rclpy.node import Node #Nodeでやり取りするのに使う？
from rclpy.logging import LoggingSeverity
from std_msgs.msg import String , Int8
from tf2_msgs.msg import TFMessage
from geometry_msgs.msg import Transform ,TransformStamped
from sensor_msgs.msg import BatteryState
import time



class TestState1Shot(Node):
    def __init__(self):
        super().__init__('test_state_1shot')

        self.declare_parameter('loglevel', "info")
        loglevel = self.get_parameter('loglevel').value
        if loglevel == "debug":
            self._logger.set_level(LoggingSeverity.DEBUG) #logの出力レベル
        else:
            self._logger.set_level(LoggingSeverity.INFO) #logの出力レベル

        # /VihicleState 初期化コマンド送信
        self.publisher_status = self.create_publisher(Int8,'/VehicleState',1)

        # テストコマンド1回送信
        self.send_test_init_status()
        


    def send_test_init_status(self):
        status_msg = Int8()
        status_msg.data = 3  # 初期ステータス: 待機中
        self.get_logger().info('Sending initial VehicleState: "%d"' % status_msg.data)
        self.publisher_status.publish(status_msg)

        time.sleep(0.1)
        status_msg.data = 3  # 初期ステータス: 待機中
        self.get_logger().info('Sending initial VehicleState: "%d"' % status_msg.data)
        self.publisher_status.publish(status_msg)

        time.sleep(0.1)
        status_msg.data = 3  # 初期ステータス: 待機中
        self.get_logger().info('Sending initial VehicleState: "%d"' % status_msg.data)
        self.publisher_status.publish(status_msg)

        time.sleep(0.1)
        status_msg.data = 1  # 初期ステータス: 移動中
        self.get_logger().info('Sending initial VehicleState: "%d"' % status_msg.data)
        self.publisher_status.publish(status_msg)

        time.sleep(0.1)
        status_msg.data = 1  # 初期ステータス: 移動中
        self.get_logger().info('Sending initial VehicleState: "%d"' % status_msg.data)
        self.publisher_status.publish(status_msg)
    
        time.sleep(0.1)
        status_msg.data = 2  # 初期ステータス: マニュアル
        self.get_logger().info('Sending initial VehicleState: "%d"' % status_msg.data)
        self.publisher_status.publish(status_msg)

        time.sleep(0.1)
        status_msg.data = 1  # 初期ステータス: 移動中
        self.get_logger().info('Sending initial VehicleState: "%d"' % status_msg.data)
        self.publisher_status.publish(status_msg)

        time.sleep(0.1)
        status_msg.data = 1  # 初期ステータス: 移動中
        self.get_logger().info('Sending initial VehicleState: "%d"' % status_msg.data)
        self.publisher_status.publish(status_msg)

        time.sleep(0.1)
        status_msg.data = 11  # 初期ステータス: ドアオープン
        self.get_logger().info('Sending initial VehicleState: "%d"' % status_msg.data)
        self.publisher_status.publish(status_msg)

        time.sleep(0.1)
        status_msg.data = 10  # 初期ステータス: 非常停止
        self.get_logger().info('Sending initial VehicleState: "%d"' % status_msg.data)
        self.publisher_status.publish(status_msg)

        time.sleep(0.1)
        status_msg.data = 12  # 初期ステータス: lidar検知
        self.get_logger().info('Sending initial VehicleState: "%d"' % status_msg.data)
        self.publisher_status.publish(status_msg)

        time.sleep(0.1)
        status_msg.data = 1  # 初期ステータス: 移動中
        self.get_logger().info('Sending initial VehicleState: "%d"' % status_msg.data)
        self.publisher_status.publish(status_msg)

        time.sleep(0.1)
        status_msg.data = 1  # 初期ステータス: 移動中
        self.get_logger().info('Sending initial VehicleState: "%d"' % status_msg.data)
        self.publisher_status.publish(status_msg)

        time.sleep(0.1)
        status_msg.data = 0  # 初期ステータス: 移動完了
        self.get_logger().info('Sending initial VehicleState: "%d"' % status_msg.data)
        self.publisher_status.publish(status_msg)


        time.sleep(0.1)
        status_msg.data = 3  # 初期ステータス: 待機中
        self.get_logger().info('Sending initial VehicleState: "%d"' % status_msg.data)
        self.publisher_status.publish(status_msg)








def main(args=None):
    print('Hi from test_state_1shot.')

    rclpy.init(args=args)   #初期化　絶対書く

    node = TestState1Shot()
    rclpy.spin(node)  # 終了まで待機
    node.destroy_node() #ノードの破壊
    rclpy.shutdown() # 終了処理

if __name__ == '__main__':
    main()