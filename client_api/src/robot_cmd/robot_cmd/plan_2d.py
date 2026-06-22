#!/usr/bin/env python3

import rclpy #ROS2 を Python で開発する場合必須
from rclpy.node import Node #Nodeでやり取りするのに使う？
from rclpy.logging import LoggingSeverity
from std_msgs.msg import String #Json(String)をいつも使うので
from nav_msgs.msg import Path
from geometry_msgs.msg import PoseStamped
import json
import tf_transformations
from geometry_msgs.msg import Quaternion
import math
from custom_msgs.srv import  StateCheck
from custom_msgs.action import Plan2D
from action_msgs.msg import GoalStatus
from rclpy.action import ActionClient


class Plan2DClass(Node):
    def __init__(self):
        super().__init__('plan_2d')

        self.declare_parameter('loglevel', "info")
        loglevel = self.get_parameter('loglevel').value
        if loglevel == "debug":
            self._logger.set_level(LoggingSeverity.DEBUG) #logの出力レベル
        else:
            self._logger.set_level(LoggingSeverity.INFO) #logの出力レベル


        #変数初期化
        self.response_json = {}
        self.move_order = []
        self.move_id = {}
        self.move_point = 0


        # ClinetAPI からの大局経路コマンド
        self.sub = self.create_subscription(String,'/client_api/plan_2d',self._2d_plan_callback,3)
        # ClientAPI のレスポンス
        self.response_pub = self.create_publisher(String,'/client_api/plan_2d/response',3)
        # ステータスノードへの現在ステータス確認
        self.status_check_srv = self.create_client(StateCheck,'/client_api/srv/state_check')
        # ロボットの大局経路
        self.robot_pub = self.create_publisher(Path,'/plan',3)
        # ステータス待機アクション
        self.status_action = ActionClient(self,Plan2D,'/client_api/action/plan_2d')
        while not self.status_check_srv.wait_for_service(timeout_sec=1.0):
            self.get_logger().info('service not available, waiting again...')
        while not self.status_action.wait_for_server(timeout_sec=1.0):
            self.get_logger().info('action server not available, waiting again...')


    # 大局経路コマンド受信コールバック
    def _2d_plan_callback(self,msg):
        _json = json.loads(msg.data)
        self.get_logger().info('Received 2dPlan cmd: "%s"' % str(_json))

        # 受け取ったら受信応答
        move_order = _json["move_order"]  # move_orderは配列情報
        response_json = {
            "ID" : {
                "robot_name": _json["ID"]["robot_name"],
                "UUID": _json["ID"]["UUID"],
                "type": _json["ID"]["type"]
            },
            "serial_number": move_order[0]["serial_number"],
            "response_code": 0
        }
        self.response_pub.publish(String(data=json.dumps(response_json)))
        self.get_logger().info('Published 2dPlan initial response: "%s"' % json.dumps(response_json))

        # ステータスを確認
        state_chack = self.status_check_srv.call_async(StateCheck.Request(order_type=_json["ID"]["type"]))
        self.response_json = response_json
        self.move_order = move_order
        self.move_id = _json["ID"]
        #　非同期コールバック登録(そうしないと応答が帰ってこない)
        state_chack.add_done_callback(self.status_check_response_callback)

    # 非同期コールバック
    def status_check_response_callback(self,future):
        state_chack = future
        if state_chack.result() is not None:
            self.get_logger().info('Status check response received: "%s"' % str(state_chack.result().response))
            # レスポンス状態によって命令を開始するか、異常を返すか決める
            
            response = state_chack.result().response
            response_code = state_chack.result().response_code
            if response != True:
                self.get_logger().warning('Cannot start 2D Plan, invalid status. response_code=%d' % response_code)
                self.response_json["response_code"] = response_code
                self.response_pub.publish(String(data=json.dumps(self.response_json)))
                # 変数初期化
                self.response_json = {}
                self.move_order = []
                self.move_id = {}
                self.move_point = 0
                return
            else:
                pass
        else:
            self.get_logger().error('Service call failed %r' % (state_chack.exception(),))
            #サービス失敗したので実行失敗を返して終了
            self.response_json["response_code"] = 12
            self.response_pub.publish(String(data=json.dumps(self.response_json)))
            # 変数初期化
            self.response_json = {}
            self.move_order = []
            self.move_id = {}
            self.move_point = 0
            return

        # ロボットに移動先を通知
        plan_msg = Path()
        plan_msg.header.frame_id = "map"
        for pose in self.move_order:
            pose_msg = PoseStamped()
            pose_msg.header.frame_id = "map"
            pose_msg.pose.position.x = pose["x"]
            pose_msg.pose.position.y = pose["y"]
            pose_msg.pose.position.z = pose["z"]
            q = self.euler_to_quaternion(pose["t"])
            pose_msg.pose.orientation.x = q.x
            pose_msg.pose.orientation.y = q.y
            pose_msg.pose.orientation.z = q.z
            pose_msg.pose.orientation.w = q.w
            plan_msg.poses.append(pose_msg)

        
        self.robot_pub.publish(plan_msg)
        self.get_logger().info('Published 2D Plan to robot: "%s"' % str(plan_msg))

        # ステータス監視に移行
        # 走行中を監視、それ以外になったらレスポンスがある
        self.send_action_goal_async(self.move_id, len(self.move_order))


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
    def send_action_goal_async(self, id, point_list=None):
        goal_msg = Plan2D.Goal()
        goal_msg.id = id["UUID"]
        goal_msg.move_point_list = point_list
        self.get_logger().info('[1]Sending action goal...')
        self._goal_handle = self.status_action.send_goal_async(goal_msg, feedback_callback=self.action_feedback_callback)
        self._goal_handle.add_done_callback(self.action_goal_response_callback)

    #　アクションのフィードバック受信
    def action_feedback_callback(self, feedback_msg):
        feedback = feedback_msg.feedback
        #フィードバック中
        if not self.move_order or feedback.move_pont >= len(self.move_order):
            self.get_logger().warning('[3]Invalid feedback: move_order is empty or move_pont is out of range')
            #変数初期化
            self.response_json = {}
            self.move_order = []
            self.move_id = {}
            self.move_point = 0
            return
        self.get_logger().debug('[3]Received action feedback: robot_state="%s", serial_number="%d", plan_status="%d"' % (feedback.status, self.move_order[feedback.move_pont]["serial_number"], feedback.plan_status))
        self.move_point = feedback.move_pont
        # status を確認して中継地点を経由していることをレスポンスで送る
        if feedback.plan_status == 3: #中継地点到達
            self.response_json["response_code"] = 3
            self.response_json["serial_number"] = self.move_order[feedback.move_pont]["serial_number"]
            response_str = json.dumps(self.response_json)
            self.response_pub.publish(String(data=response_str))
            self.get_logger().info('[3]Published plan2D response: "%s"' % response_str)




    # アクションゴールのレスポンス受信
    def action_goal_response_callback(self, future):
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.get_logger().error('[2]Action goal rejected')
            self.response_json["response_code"]  = 13
            response_str = json.dumps(self.response_json)
            self.response_pub.publish(String(data=response_str))
            self.get_logger().info('Published plan2D response: "%s"' % response_str)
            #変数初期化
            self.response_json = {}
            self.move_order = []
            self.move_id = {}
            self.move_point = 0
            return

        self.get_logger().info('[2]Action goal accepted, waiting for result...')
        get_result_future = goal_handle.get_result_async()
        get_result_future.add_done_callback(self.action_result_callback)


    # アクション結果受信
    def action_result_callback(self, future):
        result = future.result().result
        status = future.result().status

        try:
            if status == GoalStatus.STATUS_SUCCEEDED:
                self.get_logger().info('[fin]Action result received: response_code="%d"' % result.response_code)
                self.response_json["response_code"]  = result.response_code
                self.response_json["serial_number"] = self.move_order[-1]["serial_number"] #最後の番号を返す
            else:
                self.get_logger().error('[fin]Action failed with status: %d' % status)
                self.response_json["response_code"]  = result.response_code
                self.response_json["serial_number"] = self.move_order[self.move_point]["serial_number"]

            response_str = json.dumps(self.response_json)
            self.response_pub.publish(String(data=response_str))
            self.get_logger().info('Published plan2D response: "%s"' % response_str)

        except Exception as e:
            self.get_logger().error(f'[fin]Exception in action result callback: {e}')

        finally:
            # 次のコマンドを受け付けられるようクライアント状態を初期化
            self.response_json = {}
            self.move_order = []
            self.move_id = {}
            self.move_point = 0
            pass


def main(args=None):
    print('Hi from plan_2d.')

    rclpy.init(args=args)   #初期化　絶対書く

    node = Plan2DClass()
    rclpy.spin(node)  # 終了まで待機
    node.destroy_node() #ノードの破壊
    rclpy.shutdown() # 終了処理


if __name__ == '__main__':
    main()