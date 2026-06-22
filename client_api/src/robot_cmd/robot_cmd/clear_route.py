import rclpy #ROS2 を Python で開発する場合必須
from rclpy.node import Node #Nodeでやり取りするのに使う？
from rclpy.logging import LoggingSeverity
from std_msgs.msg import String #Json(String)をいつも使うので
from std_msgs.msg import Int8 
import json
from rclpy.action import ActionClient
from action_msgs.msg import GoalStatus
from custom_msgs.srv import  StateCheck
from custom_msgs.action import CancelRoute


class clearRoute(Node):
    def __init__(self):
        super().__init__('clear_route') #Nodeの生成、引数はノード名 オリジンで管理が必要

        self.declare_parameter('loglevel', "info")
        loglevel = self.get_parameter('loglevel').value
        if loglevel == "debug":
            self._logger.set_level(LoggingSeverity.DEBUG) #logの出力レベル
        else:
            self._logger.set_level(LoggingSeverity.INFO) #logの出力レベル

        #変数初期化
        self.response_json = {}
        self.clear_id = {}

        # ClinetAPI からのクリアルートコマンド
        self.sub = self.create_subscription(String,'/client_api/goal_2dcancel',self.clear_route_callback,3)
        # ClientAPI のレスポンス
        self.response_pub = self.create_publisher(String,'/client_api/goal_2dcancel/response',3)
        # ステータスノードへの移動中ステータス確認
        self.move_check_srv = self.create_client(StateCheck,'/client_api/srv/state_check')
        # ロボットの移動キャンセルタスクパブリッシャー
        self.pub = self.create_publisher(Int8,'/task',3)
        # ステータス待機アクション
        self.status_action = ActionClient(self,CancelRoute,'/client_api/action/clear_route')
        while not self.move_check_srv.wait_for_service(timeout_sec=1.0):
            self.get_logger().info('service not available, waiting again...')
        while not self.status_action.wait_for_server(timeout_sec=1.0):
            self.get_logger().info('action server not available, waiting again...')
        
    # クリアルートコマンド受信コールバック
    def clear_route_callback(self,msg):
        _json = json.loads(msg.data)
        self.get_logger().info('Received clearRoute cmd: "%s"' % str(_json))
        self.clear_id = _json["ID"]

        # 受け取ったら受信応答
        response_json = {
            "ID" : {
                "robot_name": _json["ID"]["robot_name"],
                "UUID": _json["ID"]["UUID"],
                "type": _json["ID"]["type"]
            },
            "response_code" : 0
        }
        response_str = json.dumps(response_json)
        self.response_pub.publish(String(data=response_str))
        self.get_logger().info('Published clearRoute response: "%s"' % response_str)

        # ステータスを確認
        state_chack = self.move_check_srv.call_async(StateCheck.Request(order_type=_json["ID"]["type"]))
        self.response_json = response_json

        # 非同期コールバック登録(こうしないと応答が返ってこない)
        state_chack.add_done_callback(self.move_check_response_callback)


    # 非同期コールバック
    def move_check_response_callback(self, future):
        try:
            response = future.result()
        except Exception as e:
            self.get_logger().error('Service call failed: %r' % (e,))
            self.response_json["response_code"]  = 2
            response_str = json.dumps(self.response_json)
            self.response_pub.publish(String(data=response_str))
            self.get_logger().info('Published clearRoute response: "%s"' % response_str)
            self.response_json = {}
            self.clear_id = {}
            return
        
        resp_order_type = response.order_type
        resp_response_code = response.response_code
        resp_response = response.response

        publish_flg = False

        # Trueの時、待機中にクリアルートコマンドが来た時
        # Action サーバーを呼びだしてorder_typeはリセットする、クリアルートは実行しない
        # ClientAPI レスポンス は 7: 未走行を返す
        if resp_response == True:
            self.get_logger().warn('Cannot execute clear route command. Robot is in idle state, no active route to clear.')
            publish_flg  = False
            self.response_json["response_code"]  = 7
            #response_str = json.dumps(self.response_json)
            #self.response_pub.publish(String(data=response_str))
            #self.get_logger().info('Published clearRoute response: "%s"' % response_str)

        # Falseの時、待機中以外にクリアルートコマンドが来た時
        else:
            # resp_response_code が2(失敗) の時、Actionサーバーを呼びださずに、ClientAPI レスポンスは 2:失敗を返す
            if resp_response_code == 2:
                self.get_logger().error('Cannot execute clear route command. Robot is in abnormal state.')
                self.response_json["response_code"]  = 2
                response_str = json.dumps(self.response_json)
                self.response_pub.publish(String(data=response_str))
                self.get_logger().info('Published clearRoute response: "%s"' % response_str)
                self.response_json = {}
                self.clear_id = {}
                return
            # resp_response_code が4(別命令実行中) の時、移動中にクリアルートコマンドが来た時
            elif resp_response_code == 4:
                # resp_order_type　を確認して、2D移動(0)or大局経路時(1)のみActionサーバーを呼びだす
                if resp_order_type == 0 or resp_order_type == 1:
                    self.get_logger().info('Sending clear route action request...')
                    #ここが一番想定されているパターン
                    publish_flg = True
                # それ以外の命令中(マップ切り替え,移動切り替え,位置補正,その他)にクリアルートコマンドが来た時、Actionサーバーを呼びださずに、ClientAPI レスポンスは 2:失敗を返す
                else:
                    self.get_logger().error('Cannot execute clear route command. Current active order type does not allow route clearing.')
                    self.response_json["response_code"]  = 2
                    response_str = json.dumps(self.response_json)
                    self.response_pub.publish(String(data=response_str))
                    self.get_logger().info('Published clearRoute response: "%s"' % response_str)
                    self.response_json = {}
                    self.clear_id = {}
                    return
                
            else:
                # その他不明な状態の場合、Actionサーバーを呼びださずに、ClientAPI レスポンスは 2:失敗を返す
                self.get_logger().error('Cannot execute clear route command. Unknown robot state.')
                self.response_json["response_code"]  = 2
                response_str = json.dumps(self.response_json)
                self.response_pub.publish(String(data=response_str))
                self.get_logger().info('Published clearRoute response: "%s"' % response_str)
                self.response_json = {}
                self.clear_id = {}
                return

        if publish_flg == True:
            # ロボットにクリアルートタスクを通知
            task_msg = Int8()
            task_msg.data = 1 # 1:クリアルートタスク
            self.pub.publish(task_msg)
            self.get_logger().info('Published clear route task command to robot.')

        # ステータス監視Actionサーバー呼び出し
        self.send_action_goal_async(self.clear_id, publish_flg)


    def send_action_goal_async(self, clear_id, unSkip):
        goal_msg = CancelRoute.Goal()
        goal_msg.id = clear_id["UUID"]
        goal_msg.un_skip = unSkip
        self.get_logger().info('[1]Sending clear route action request...')
        send_goal_future = self.status_action.send_goal_async(goal_msg, feedback_callback=self.action_feedback_callback)
        send_goal_future.add_done_callback(self.clear_route_goal_response_callback)

    def action_feedback_callback(self, feedback_msg):
        feedback = feedback_msg.feedback
        # 待機中フィードバック受信
        self.get_logger().info('[3]Received clear route action feedback: status="%d"' % feedback.status)

    def clear_route_goal_response_callback(self, future):
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.get_logger().info('[2]Clear route action goal rejected.')
            return

        self.get_logger().info('[2]Clear route action goal accepted.')
        get_result_future = goal_handle.get_result_async()
        get_result_future.add_done_callback(self.clear_route_result_callback)


    def clear_route_result_callback(self, future):
        result = future.result().result
        status = future.result().status

        try:
            if status == GoalStatus.STATUS_SUCCEEDED:
                self.get_logger().info('[fin]Clear route action succeeded.')
            else:
                self.get_logger().info('[fin]Clear route action failed with status: %d' % status)

            # 受信時に作った応答JSONへ最終コードを反映
            if isinstance(self.response_json, dict):
                # CancelRoute.Result は response_code を持つ
                self.response_json["response_code"] = getattr(result, 'response_code', 2)
                self.response_pub.publish(String(data=json.dumps(self.response_json)))
                self.get_logger().info('Published clearRoute response: "%s"' % json.dumps(self.response_json))
        finally:
            # 次のコマンドを受け付けられるようクライアント状態を初期化
            self.response_json = {}
            self.clear_id = {}




def main(args=None):
    print('Hi from clear_route.')

    rclpy.init(args=args)   #初期化　絶対書く

    node = clearRoute()
    rclpy.spin(node)  # 終了まで待機
    node.destroy_node() #ノードの破壊
    rclpy.shutdown() # 終了処理


if __name__ == '__main__':
    main()