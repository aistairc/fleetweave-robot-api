import rclpy #ROS2 を Python で開発する場合必須
from rclpy.node import Node #Nodeでやり取りするのに使う？
from rclpy.logging import LoggingSeverity
from std_msgs.msg import String #Json(String)をいつも使うので
from geometry_msgs.msg import PoseWithCovarianceStamped
import json
from custom_msgs.srv import  StateCheck
import tf_transformations
from geometry_msgs.msg import Quaternion
import math


class InitPose(Node):
    def __init__(self):
        super().__init__('init_pose')

        self.declare_parameter('loglevel', "info")
        loglevel = self.get_parameter('loglevel').value
        if loglevel == "debug":
            self._logger.set_level(LoggingSeverity.DEBUG) #logの出力レベル
        else:
            self._logger.set_level(LoggingSeverity.INFO) #logの出力レベル


        #変数初期化
        self.response_json = {}
        self.initial_order = ""
        self.initial_id = {}


        # ClientAPI からの初期位置設定コマンド
        self.sub = self.create_subscription(String,'/client_api/initialpose',self.initialpose_callback,1)
        # ClientAPI のレスポンス
        self.response_pub = self.create_publisher(String,'/client_api/initialpose/response',3)
        # ステータスノードへの現在ステータス確認
        self.status_check_srv = self.create_client(StateCheck,'/client_api/srv/state_check')
        # ロボットの初期位置設定
        self.robot_pub = self.create_publisher(PoseWithCovarianceStamped,'/initialpose',3)
        while not self.status_check_srv.wait_for_service(timeout_sec=1.0):
            self.get_logger().info('service not available, waiting again...')
    
    # 初期位置設定コマンド受信コールバック
    def initialpose_callback(self,msg):

        _json = json.loads(msg.data)
        self.get_logger().info('Received initPose cmd: "%s"' % str(_json))

        #　受け取ったら受信応答
        initial_order = _json["initial_order"]
        response_json = {
            "ID" : {
                "robot_name": _json["ID"]["robot_name"],
                "UUID": _json["ID"]["UUID"],
                "type": _json["ID"]["type"]
            },
            "response_code": 0
        }
        self.response_pub.publish(String(data=json.dumps(response_json)))
        self.get_logger().info('Published initPose response: "%s"' % str(response_json))


        # ステータスを確認
        state_chack = self.status_check_srv.call_async(StateCheck.Request(order_type=_json["ID"]["type"]))
        self.response_json = response_json
        self.initial_order = initial_order
        self.initial_id = _json["ID"]
        # 非同期コールバック設定
        state_chack.add_done_callback(self.status_check_response_callback)


    # 非同期コールバック
    def status_check_response_callback(self,future):
        state_chack = future
        if state_chack.result() is not None:
            self.get_logger().info('Status check response received: "%d"' % state_chack.result().response)

            response = state_chack.result().response
            response_code = state_chack.result().response_code

            if response != True:
                self.get_logger().warning('Cannot process initPose command. Status check failed. response_code="%d"' % response_code)
                # ステータス異常を返す
                self.response_json["response_code"] = response_code
                self.response_pub.publish(String(data=json.dumps(self.response_json)))
                # 変数初期化
                self.response_json = {}
                self.initial_order = ""
                self.initial_id = {}
                return
        
        else:
            self.get_logger().error('Service call failed %r' % (state_chack.exception(),))
            self.response_json["response_code"] = 2
            self.response_pub.publish(String(data=json.dumps(self.response_json)))
            # 変数初期化
            self.response_json = {}
            self.initial_order = ""
            self.initial_id = {}
            return

        # 初期位置設定コマンド処理
        pose_msg = PoseWithCovarianceStamped()
        pose_msg.header.frame_id = "map"
        pose_msg.pose.pose.position.x = self.initial_order["x"]
        pose_msg.pose.pose.position.y = self.initial_order["y"]
        pose_msg.pose.pose.position.z = self.initial_order["z"]
        q = self.euler_to_quaternion(self.initial_order["t"])
        pose_msg.pose.pose.orientation.x = q.x
        pose_msg.pose.pose.orientation.y = q.y
        pose_msg.pose.pose.orientation.z = q.z
        pose_msg.pose.pose.orientation.w = q.w

        self.robot_pub.publish(pose_msg)
        self.get_logger().info('Published initial pose: x="%f", y="%f", z="%f", w="%f"' % 
                                (pose_msg.pose.pose.position.x,
                                pose_msg.pose.pose.position.y,
                                pose_msg.pose.pose.orientation.z,
                                pose_msg.pose.pose.orientation.w))


        #　今回は送らないでダミーを作ってレスポンスを返す
        rclpy.spin_once(self, timeout_sec=10.0)
        self.response_json["response_code"] = 1
        self.response_pub.publish(String(data=json.dumps(self.response_json)))
        self.get_logger().info('Published initPose completion response: "%s"' % str(self.response_json))
        # 変数初期化
        self.response_json = {}
        self.initial_order = ""
        self.initial_id = {}

    #ヨー角(degree)からクオータニオンに変換
    def euler_to_quaternion(self,yaw):
        q = tf_transformations.quaternion_from_euler(0.0, 0.0, math.radians(yaw))
        q_msg = Quaternion()
        q_msg.x = q[0]
        q_msg.y = q[1]
        q_msg.z = q[2]
        q_msg.w = q[3]
        return q_msg


def main(args=None):
    print('Hi from init_pose.')

    rclpy.init(args=args)   #初期化　絶対書く

    node = InitPose()
    rclpy.spin(node)  # 終了まで待機
    node.destroy_node() #ノードの破壊
    rclpy.shutdown() # 終了処理

if __name__ == '__main__':
    main()