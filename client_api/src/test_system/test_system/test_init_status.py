#!/usr/bin/env python3

import rclpy #ROS2 を Python で開発する場合必須
from rclpy.node import Node #Nodeでやり取りするのに使う？
from rclpy.logging import LoggingSeverity
from std_msgs.msg import String , Int8
from tf2_msgs.msg import TFMessage
from geometry_msgs.msg import Transform ,TransformStamped
from sensor_msgs.msg import BatteryState
import time



class TestInitStatus(Node):
    def __init__(self):
        super().__init__('test_init_status')

        self.declare_parameter('loglevel', "info")
        loglevel = self.get_parameter('loglevel').value
        if loglevel == "debug":
            self._logger.set_level(LoggingSeverity.DEBUG) #logの出力レベル
        else:
            self._logger.set_level(LoggingSeverity.INFO) #logの出力レベル

        # /VihicleState 初期化コマンド送信
        self.publisher_status = self.create_publisher(Int8,'/VehicleState',1)
        self.publisher_tf  = self.create_publisher(TFMessage,'/tf',1)
        self.publisher_battery = self.create_publisher(BatteryState,'/whill/states/batttery_state',1)
        self.publisher_map = self.create_publisher(Int8,'/robotMap',1)



        # テストコマンド1回送信
        self.send_test_init_status()
        


    def send_test_init_status(self):
        status_msg = Int8()
        status_msg.data = 3  # 初期ステータス: 待機中
        self.get_logger().info('Sending initial VehicleState: "%d"' % status_msg.data)
        self.publisher_status.publish(status_msg)

        time.sleep(0.5)
        tf_msg = TFMessage()
        tf_msg.transforms = []  # 初期TFメッセージ: 空
        tran = TransformStamped()
        tran.header.stamp = self.get_clock().now().to_msg()
        tran.header.frame_id = "map"
        tran.child_frame_id = "base_link"
        tran.transform.translation.x = 0.0
        tran.transform.translation.y = 0.0
        tran.transform.translation.z = 0.0
        tran.transform.rotation.x = 0.0
        tran.transform.rotation.y = 0.0
        tran.transform.rotation.z = 0.0
        tran.transform.rotation.w = 1.0
        tf_msg.transforms.append(tran)

        self.get_logger().info('Sending initial TFMessage')
        self.publisher_tf.publish(tf_msg)
        
        time.sleep(0.5)
        battery_msg = BatteryState()
        battery_msg.header.stamp = self.get_clock().now().to_msg()
        battery_msg.voltage = 12.0  # 初期バッテリーボルテージ
        battery_msg.current = 1.0   # 初期バッテリー電流
        
        battery_msg.percentage = 1.0  # 初期バッテリーステータス: フル
        self.get_logger().info('Sending initial BatteryState: "%f"' % battery_msg.percentage)
        self.publisher_battery.publish(battery_msg)

        time.sleep(0.5)
        map_msg = Int8()
        map_msg.data = 1  # 初期マップステータス: マップあり
        self.get_logger().info('Sending initial RobotMap status: "%d"' % map_msg.data)
        self.publisher_map.publish(map_msg)









def main(args=None):
    print('Hi from test_init_status.')

    rclpy.init(args=args)   #初期化　絶対書く

    node = TestInitStatus()
    rclpy.spin(node)  # 終了まで待機
    node.destroy_node() #ノードの破壊
    rclpy.shutdown() # 終了処理

if __name__ == '__main__':
    main()