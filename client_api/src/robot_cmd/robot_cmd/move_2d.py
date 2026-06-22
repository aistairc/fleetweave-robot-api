#!/usr/bin/env python3

import rclpy #ROS2 を Python で開発する場合必須
from rclpy.node import Node #Nodeでやり取りするのに使う？
from rclpy.logging import LoggingSeverity
from std_msgs.msg import String #Json(String)をいつも使うので
from geometry_msgs.msg import PoseStamped
import json
import tf_transformations
from geometry_msgs.msg import Quaternion
import math
from custom_msgs.srv import  StateCheck
from custom_msgs.action import Move2D
from action_msgs.msg import GoalStatus
from rclpy.action import ActionClient


class Move2DClass(Node):
    def __init__(self):
        super().__init__('move_2d')

        self.declare_parameter('loglevel', "info")
        loglevel = self.get_parameter('loglevel').value
        if loglevel == "debug":
            self._logger.set_level(LoggingSeverity.DEBUG) #logの出力レベル
        else:
            self._logger.set_level(LoggingSeverity.INFO) #logの出力レベル


        #変数初期化
        self.response_json = {}
        self.srv_response_json = {}
        self.move_order = ""
        self.move_id = {}


        # ClinetAPI からの2D移動コマンド
        self.sub = self.create_subscription(String,'/client_api/goal_2d',self._2d_move_callback,3)
        # ClientAPI のレスポンス
        self.response_pub = self.create_publisher(String,'/client_api/goal_2d/response',3)
        # ステータスノードへの現在ステータス確認
        self.status_check_srv = self.create_client(StateCheck,'/client_api/srv/state_check')
        # ロボットの2D移動
        self.robot_pub = self.create_publisher(PoseStamped,"/goal2d",3)
        # ステータス待機アクション
        self.status_action = ActionClient(self,Move2D,'/client_api/action/move_2d')
        while not self.status_check_srv.wait_for_service(timeout_sec=1.0):
            self.get_logger().info('service not available, waiting again...')
        while not self.status_action.wait_for_server(timeout_sec=1.0):
            self.get_logger().info('action server not available, waiting again...')

    # 2D移動コマンド受信コールバック
    def _2d_move_callback(self,msg):
        _json = json.loads(msg.data)
        self.get_logger().info('Received 2dMove cmd: "%s"' % str(_json))

        # 受け取ったら受信応答
        move_order = _json["move_order"][0]
        response_json = {
            "ID" : {
                "robot_name": _json["ID"]["robot_name"],
                "UUID": _json["ID"]["UUID"],
                "type": _json["ID"]["type"]
            },
            "serial_number": move_order["serial_number"],
            "response_code": 0
        }
        self.response_pub.publish(String(data=json.dumps(response_json)))
        self.get_logger().info('Published move2D initial response: "%s"' % json.dumps(response_json))

        # ステータスを確認
        state_chack = self.status_check_srv.call_async(StateCheck.Request(order_type=_json["ID"]["type"]))
        #self.response_json = response_json
        self.srv_response_json = response_json
        self.move_order = move_order
        self.move_id = _json["ID"]
        #　非同期コールバック登録(そうしないと応答が帰ってこない)
        state_chack.add_done_callback(self.status_check_response_callback)

    # 非同期コールバック
    def status_check_response_callback(self, future):
        state_chack = future
        if state_chack.result() is not None:
            self.get_logger().info('Service response received: "%d"' % state_chack.result().response)
            # レスポンス状態によって命令を開始するか、異常を返すか決める
            #　この時点でステータス側は2D移動をハンドリング、ステータスは待機状態
            response = state_chack.result().response
            response_code = state_chack.result().response_code
            if response != True:
                self.get_logger().error('Cannot execute move command. Current robot state does not allow movement.')
                self.srv_response_json["response_code"]  = response_code
                self.response_pub.publish(String(data=json.dumps(self.srv_response_json)))
                #変数初期化
                #self.response_json = {}
                self.srv_response_json = {}
                self.move_order = ""
                self.move_id = {}
                return
        else:
            self.get_logger().error('Service call failed %r' % (state_chack.exception(),))
            #サービス失敗したので実行失敗を返して終了
            self.srv_response_json["response_code"] = 12
            self.response_pub.publish(String(data=json.dumps(self.srv_response_json)))
            #変数初期化
            #self.response_json = {}
            self.srv_response_json = {}
            self.move_order = ""
            self.move_id = {}
            return

        self.response_json = self.srv_response_json

        #ロボットに移動先を通知
        pose_msg = PoseStamped()
        pose_msg.header.frame_id = "map"
        pose_msg.pose.position.x = self.move_order["x"]
        pose_msg.pose.position.y = self.move_order["y"]
        pose_msg.pose.position.z = self.move_order["z"]
        q = self.euler_to_quaternion(self.move_order["t"])
        pose_msg.pose.orientation.x = q.x
        pose_msg.pose.orientation.y = q.y
        pose_msg.pose.orientation.z = q.z
        pose_msg.pose.orientation.w = q.w
        self.robot_pub.publish(pose_msg)


        self.get_logger().info('Published 2D goal: x="%f", y="%f", z="%f", w="%f"' % 
                                (pose_msg.pose.position.x,
                                pose_msg.pose.position.y,
                                pose_msg.pose.orientation.z,
                                pose_msg.pose.orientation.w))
        
        #　ステータス監視に移行
        #  走行中を監視、それ以外になったらレスポンスがある
        self.send_action_goal_async(self.move_id)


    #ヨー角(degree)からクオータニオンに変換
    def euler_to_quaternion(self,yaw):
        q = tf_transformations.quaternion_from_euler(0.0, 0.0, math.radians(yaw))
        q_msg = Quaternion()
        q_msg.x = q[0]
        q_msg.y = q[1]
        q_msg.z = q[2]
        q_msg.w = q[3]
        return q_msg
    
    # アクションゴール送信(非同期)
    def send_action_goal_async(self, id):
        goal_msg = Move2D.Goal()
        goal_msg.id = id["UUID"]
        self.get_logger().info('[1]Sending action goal...')
        self._action_goal_future = self.status_action.send_goal_async(goal_msg, feedback_callback=self.action_feedback_callback)
        self._action_goal_future.add_done_callback(self.action_goal_response_callback)
    
    #　アクションのフィードバック受信
    def action_feedback_callback(self, feedback_msg):
        feedback = feedback_msg.feedback
        #待機中はこれが流れる
        self.get_logger().debug('[3]Received action feedback: current_state="%s"' % feedback.status)

    # アクションゴールのレスポンス受信
    def action_goal_response_callback(self, future):
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.get_logger().error('[2]Action goal rejected')
            self.response_json["response_code"]  = 13
            response_str = json.dumps(self.response_json)
            self.response_pub.publish(String(data=response_str))
            self.get_logger().info('Published move2D response: "%s"' % response_str)
            #変数初期化
            self.response_json = {}
            #self.srv_response_json = {}
            self.move_order = ""
            self.move_id = {}
            return

        self.get_logger().info('[2]Action goal accepted')
        self._action_result_future = goal_handle.get_result_async()
        self._action_result_future.add_done_callback(self.action_result_callback)
    
    # アクション結果受信
    def action_result_callback(self, future):
        result = future.result().result
        status = future.result().status
        # 最終レスポンスをPublishして状態をクリア
        try:
            if status == GoalStatus.STATUS_SUCCEEDED:
                self.get_logger().info('[fin]Action succeeded')
            else:
                self.get_logger().info('[fin]Action failed with status: %d' % status)

            # 受信時に作った応答JSONへ最終コードを反映
            if isinstance(self.response_json, dict):
                # Move2D.Result は response_code を持つ
                self.response_json["response_code"] = getattr(result, 'response_code', 2)
                self.response_pub.publish(String(data=json.dumps(self.response_json)))
                self.get_logger().info('Published move2D response: "%s"' % json.dumps(self.response_json))
        finally:
            # 次のコマンドを受け付けられるようクライアント状態を初期化
            self.response_json = {}
            #self.srv_response_json = {}
            self.move_order = ""
            self.move_id = {}



def main(args=None):
    print('Hi from move_2d.')

    rclpy.init(args=args)   #初期化　絶対書く

    node = Move2DClass()
    rclpy.spin(node)  # 終了まで待機
    node.destroy_node() #ノードの破壊
    rclpy.shutdown() # 終了処理


if __name__ == '__main__':
    main()