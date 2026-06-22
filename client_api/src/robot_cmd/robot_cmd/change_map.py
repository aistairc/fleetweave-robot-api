#!/usr/bin/env python3

import rclpy #ROS2 を Python で開発する場合必須
from rclpy.node import Node #Nodeでやり取りするのに使う？
from rclpy.logging import LoggingSeverity
from std_msgs.msg import String #Json(String)をいつも使うので
from std_msgs.msg import Int8
import json
from action_msgs.msg import GoalStatus
from rclpy.action import ActionClient
from custom_msgs.srv import  StateCheck
from custom_msgs.action import ChangeMap


class ChangeMapClass(Node):
    def __init__(self):
        super().__init__('change_map')

        self.declare_parameter('loglevel', "info")
        loglevel = self.get_parameter('loglevel').value
        if loglevel == "debug":
            self._logger.set_level(LoggingSeverity.DEBUG) #logの出力レベル
        else:
            self._logger.set_level(LoggingSeverity.INFO) #logの出力レベル

        #変数初期化
        self.response_json = {}
        self.change_map_int = -1
        self.is_processing = False  # 処理中フラグを追加
        self._get_result_future = None  # アクション結果のfutureを初期化


        # ClinetAPI からのマップ変更コマンド
        self.sub = self.create_subscription(String,'/client_api/robotMapChange',self.change_map_callback,3)
        # ClientAPI のレスポンス
        self.response_pub = self.create_publisher(String,'/client_api/robotMapChange/response',3)
        # ステータスノードへの移動中ステータス確認
        self.move_check_srv = self.create_client(StateCheck,'/client_api/srv/state_check')
        # ロボットのマップ変更パブリッシャー
        self.pub = self.create_publisher(Int8,'/robotMapChange',3)
        # マップ変更アクション
        self.change_map_action = ActionClient(self,ChangeMap,'/client_api/action/change_map')
        while not self.move_check_srv.wait_for_service(timeout_sec=1.0):
            self.get_logger().info('service not available, waiting again...')
        while not self.change_map_action.wait_for_server(timeout_sec=1.0):
            self.get_logger().info('action server not available, waiting again...')

    # マップ変更コマンド受信コールバック
    def change_map_callback(self,msg):
        # 処理中の場合は新しいリクエストを拒否
        if self.is_processing:
            self.get_logger().warning('Map change already in progress, rejecting new request')
            response_json = {"response_code": 2}
            self.response_pub.publish(String(data=json.dumps(response_json)))
            return
        
        _json = json.loads(msg.data)
        self.get_logger().info('Received changeMap cmd: "%s"' % str(_json))

        # 受け取ったら受信応答
        change_map_name = _json["map"]
        self.change_map_int = self.map_string_to_int(change_map_name)

        #　map名が不正ならレスポンスを返して終了
        if self.change_map_int == -1:
            response_json = {
                "response_code" : 5
            }
            response_str = json.dumps(response_json)
            self.response_pub.publish(String(data=response_str))
            self.get_logger().info('Published changeMap response: "%s"' % response_str)
            return

        # 処理開始フラグを立てる
        self.is_processing = True
        
        self.response_json = {
            "response_code" : 0
        }

        response_msg = String()
        response_msg.data = json.dumps(self.response_json)
        self.response_pub.publish(response_msg)
        self.get_logger().info('Published changeMap response: "%s"' % str(self.response_json))

        # ステータスを確認
        state_chack = self.move_check_srv.call_async(StateCheck.Request(order_type=10))

        # 非同期コールバック
        state_chack.add_done_callback(self.change_map_response_callback)
        self.get_logger().info('Called state check service for map change.')

    # ステータス確認サービスコールバック
    def change_map_response_callback(self, future):
        try:
            response = future.result()
            self.get_logger().info('State check service response received: order_type=%d, response_code=%d, response=%s' % (response.order_type, response.response_code, str(response.response)))
            resp_order_type = response.order_type
            resp_response_code = response.response_code
            resp_response = response.response

            # Trueならマップ変更実行(待機中のため)
            if resp_response == True:
                pass
            else:
                # false時、response_codeが4の場合エラーを6で返す
                if resp_response_code == 4:
                    self.response_json["response_code"]  = 6
                    response_str = json.dumps(self.response_json)
                    self.response_pub.publish(String(data=response_str))
                    self.get_logger().info('Published changeMap response: "%s"' % response_str)
                else:
                    self.response_json["response_code"]  = 2
                    response_str = json.dumps(self.response_json)
                    self.response_pub.publish(String(data=response_str))
                    self.get_logger().info('Published changeMap response: "%s"' % response_str)
                #変数初期化
                self.response_json = {}
                self.change_map_int = -1
                self.is_processing = False  # 処理終了フラグをクリア
                return
            
            # マップ変更コマンドをロボットに通知
            map_msg = Int8()
            map_msg.data = self.change_map_int
            self.pub.publish(map_msg)
            self.get_logger().info('Published map change to robot: "%d"' % self.change_map_int)

            # マップ名監視に移行
            self.send_action_goal_async(self.change_map_int)
            

        except Exception as e:
            self.get_logger().error('Map change action failed: %s' % str(e))
            self.response_json["response_code"]  = 2
            response_str = json.dumps(self.response_json)
            self.response_pub.publish(String(data=response_str))
            self.get_logger().info('Published changeMap response: "%s"' % response_str)
            #変数初期化
            self.response_json = {}
            self.change_map_int = -1
            self.is_processing = False  # 処理終了フラグをクリア
            self._get_result_future = None  # futureをクリア
            return
                                           
    def map_string_to_int(self, map_name):
        map_dict = {
            "buildingA" : 0,
            "road"      : 1,
            "buildingB" : 2
        }
        # dictになければ-1を返す
        return map_dict.get(map_name, -1)
    
    # アクションゴール送信(非同期)
    def send_action_goal_async(self, change_map_id):
        # 前回のfutureをクリア
        self._get_result_future = None
        
        goal_msg = ChangeMap.Goal()
        goal_msg.map_id = change_map_id
        self.get_logger().info('[1]Sending map change action request...')
        send_goal_future = self.change_map_action.send_goal_async(goal_msg, feedback_callback=self.action_feedback_callback)
        send_goal_future.add_done_callback(self.action_goal_response_callback)

    # アクションのフィードバック受信
    def action_feedback_callback(self, feedback_msg):
        feedback = feedback_msg.feedback
        # 待機中フィードバック受信
        self.get_logger().info('[3]Received map change action feedback: status="%d"' % feedback.status)

    def action_goal_response_callback(self, future):
        try:
            goal_handle = future.result()
            if not goal_handle.accepted:
                self.get_logger().error('[2]Map change action goal rejected')
                self.response_json["response_code"]  = 2
                response_str = json.dumps(self.response_json)
                self.response_pub.publish(String(data=response_str))
                self.get_logger().info('[2]Published changeMap response: "%s"' % response_str)
                #変数初期化
                self.response_json = {}
                self.change_map_int = -1
                self.is_processing = False  # 処理終了フラグをクリア
                self._get_result_future = None  # futureをクリア
                return

            self.get_logger().info('[2]Map change action goal accepted')
            self._get_result_future = goal_handle.get_result_async()
            self._get_result_future.add_done_callback(self.change_map_result_callback)

        except Exception as e:
            self.get_logger().error('Service call failed %r' % (e,))
            self.response_json["response_code"]  = 2
            response_str = json.dumps(self.response_json)
            self.response_pub.publish(String(data=response_str))
            self.get_logger().info('Published changeMap response: "%s"' % response_str)
            #変数初期化
            self.response_json = {}
            self.change_map_int = -1
            self.is_processing = False  # 処理終了フラグをクリア
            self._get_result_future = None  # futureをクリア
            return
        
    # アクション結果受信
    def change_map_result_callback(self, future):
        result = future.result().result
        status = future.result().status
        # 最終レスポンスをPublishして状態をクリア
        try:
            if status == GoalStatus.STATUS_SUCCEEDED:
                self.get_logger().info('[fin]Map change action succeeded')
            else:
                self.get_logger().info('[fin]Map change action failed with status: %d' % status)

            # 受信時に作った応答JSONへ最終コードを反映
            if isinstance(self.response_json, dict):
                # ChangeMap.Result は response_code を持つ
                self.response_json["response_code"] = getattr(result, 'response_code', 2)
                self.response_pub.publish(String(data=json.dumps(self.response_json)))
                self.get_logger().info('Published changeMap response: "%s"' % json.dumps(self.response_json))
        finally:
            # 次のコマンドを受け付けられるようクライアント状態を初期化
            self.response_json = {}
            self.change_map_int = -1
            self.is_processing = False  # 処理終了フラグをクリア
            self._get_result_future = None  # futureをクリア

def main(args=None):
    rclpy.init(args=args)

    change_map_node = ChangeMapClass()

    rclpy.spin(change_map_node)

    change_map_node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()