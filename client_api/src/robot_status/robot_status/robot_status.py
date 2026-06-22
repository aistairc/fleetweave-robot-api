import rclpy #ROS2 を Python で開発する場合必須
from rclpy.node import Node #Nodeでやり取りするのに使う？
from rclpy.logging import LoggingSeverity
from std_msgs.msg import String #Json(String)をいつも使うので
from sensor_msgs.msg import BatteryState
from std_msgs.msg import Int8
from tf2_msgs.msg import TFMessage
import tf_transformations
import math
import json
from custom_msgs.srv import  StateCheck
from robot_status.action_2dmove import Action2DMove
from robot_status.action_2dplan import Action2DPlan
from robot_status.action_clearroute import ActionClearRoute
from robot_status.action_changemap import ActionChangeMap

'''
/tf からmap->base_linkの情報を取得して現在地にする
  orientationはヨー角(degree)に変換する
/battery_state から電池の状態を取得する
/VehicleState からロボットの状態を取得する
複数の情報を纏める

'''


class RobotStatus(Node):
    def __init__(self):
        super().__init__('robot_status')

        self.declare_parameter('loglevel', "info")
        loglevel = self.get_parameter('loglevel').value
        if loglevel == "debug":
            self._logger.set_level(LoggingSeverity.DEBUG) #logの出力レベル
        else:
            self._logger.set_level(LoggingSeverity.INFO) #logの出力レベル

        # イベント受付窓口
        # ROS2　Sub
        self.tf_sub = self.create_subscription(TFMessage,'/tf',self.status_callback,3)
        self.battery_sub = self.create_subscription(BatteryState,'/whill/states/batttery_state',self.battery_callback,3)
        self.status_sub = self.create_subscription(Int8,'/VehicleState',self.robot_callback,3)
        self.map_sub = self.create_subscription(Int8,'/robotMap',self.map_callback,3)

        self.pub = self.create_publisher(String,'/client_api/robotStatus',3)

        self.status_json = None   # 現在地情報
        self.battery_json = None  # 電池情報
        self.robot_status = None  # ロボット状態
        self.robot_state_published = True #ステータスを一度でもPubしたか
        self.robot_state_len = []  # ステータス履歴保存用
        self.use_order_type = None  # 現在使用中の命令タイプ
        self.map_name = None

        self.cancel_flag = False
        self.plan_2d_status = None #大局経路中のステータス(本来のステータス)
        self.plan_completed_cnt = 0 #中継到着回数

        #イベントステータスサーバー
        self.srv_status_check = self.create_service(StateCheck,'/client_api/srv/state_check',self.srv_status_check_callback)

        # 2D移動アクションサーバー
        self.action_2dmove = Action2DMove(self)
        # クリアルートアクションサーバー
        self.action_clearroute = ActionClearRoute(self)
        # マップ変更アクションサーバー
        self.action_changemap = ActionChangeMap(self)
        # 2D大局経路アクションサーバー
        self.action_2dplan = Action2DPlan(self)
        # タイマーコールバックの設定
        self.timer = self.create_timer(5.0, self.timer_callback)

    #　TFメッセージコールバック
    def status_callback(self,msg:TFMessage):
        for transform in msg.transforms:
            if (transform.header.frame_id == "map") and (transform.child_frame_id == "base_link"):
                pos = transform.transform.translation
                ori = transform.transform.rotation
                self.status_json = {
                    "position": {
                        "x": pos.x,
                        "y": pos.y,
                        "z": pos.z
                    },
                    "orientation": {
                        "x": ori.x,
                        "y": ori.y,
                        "z": ori.z,
                        "w": ori.w
                    }
                }
                self.get_logger().debug('Current Robot Status: "%s"' % json.dumps(self.status_json))

    # 電池状態メッセージコールバック
    def battery_callback(self,msg):
        try:
            self.get_logger().debug('Received Battery msg: "%s"' % str(msg))
            # 電池の状態
            power_supply_status = msg.power_supply_status
            if (power_supply_status == 0):
                power_supply_status_str = "UNKNOWN"
            elif (power_supply_status == 1):
                power_supply_status_str = "CHARGING"                   #充電中
            elif (  power_supply_status == 2):
                power_supply_status_str = "DISCHARGING"                #放電中
            elif (power_supply_status == 3):
                power_supply_status_str = "NOT_CHARGING"               #充電されていない
            elif (power_supply_status == 4):
                power_supply_status_str = "FULL"                       #満充電
            else:
                power_supply_status_str = "INVALID"

            # 電池の健康状態
            power_supply_health = msg.power_supply_health
            if (power_supply_health == 0):
                power_supply_health_str = "UNKNOWN"                    #不明
            elif (power_supply_health == 1):
                power_supply_health_str = "GOOD"                       #良好
            elif (power_supply_health == 2):
                power_supply_health_str = "OVERHEAT"                   #温度異常
            elif (power_supply_health == 3):
                power_supply_health_str = "DEAD"                       #寿命
            elif (power_supply_health == 4):
                power_supply_health_str = "OVER_VOLTAGE"               #過電圧
            elif (power_supply_health == 5):
                power_supply_health_str = "UNSPEC_FAILURE"             #特定不能な故障
            elif (power_supply_health == 6):
                power_supply_health_str = "COLD"                       #低温
            elif (power_supply_health == 7):
                power_supply_health_str = "WATCHDOG_TIMER_EXPIRE"      #監視タイマー期限切れ
            elif (power_supply_health == 8):
                power_supply_health_str = "SAFETY_TIMER_EXPIRE"        #安全タイマー期限切れ
            else:
                power_supply_health_str = "INVALID"

            # 電池の種類
            power_supply_technology = msg.power_supply_technology
            if (power_supply_technology == 0):
                power_supply_technology_str = "UNKNOWN"
            elif (power_supply_technology == 1):
                power_supply_technology_str = "NIMH"                   #ニッケル水素電池
            elif (power_supply_technology == 2):
                power_supply_technology_str = "LION"                   #リチウムイオン電池
            elif (power_supply_technology == 3):
                power_supply_technology_str = "LIPO"                   #リチウムポリマー電池
            elif (power_supply_technology == 4):
                power_supply_technology_str = "LIFE"                   #リチウムイオン鉄電池
            elif (power_supply_technology == 5):
                power_supply_technology_str = "NICD"                   #ニッカド電池
            elif (power_supply_technology == 6):
                power_supply_technology_str = "LIMN"                   #リチウムマンガン電池
            else:
                power_supply_technology_str = "INVALID"

            voltage = msg.voltage          # 電圧[V]
            current = msg.current          # 電流[A]
            percentage = msg.percentage *100   # 残量[%]
            charge = msg.charge            # 充電量[Ah]
            capacity = msg.capacity        # 容量[Ah]
            design_capacity = msg.design_capacity  # 設計容量[Ah]


            self.battery_json = {
                "level": percentage,
                "power_supply" : 3
            }

        except Exception as e:
            self.get_logger().error('Error in battery_callback: %s' % str(e))

    # ロボットステータスメッセージコールバック
    def robot_callback(self,msg:Int8):
        # ロボットの状態取得
        # ステータス変化を検知する、一度Pubしなければステータスを更新してはいけない
        state = msg.data

        if self.use_order_type == 1:
            # 大局経路中は移動完了を受け取ってもここで変更できない
            if state == 0: #移動完了
                if self.plan_2d_status != 0: # 何回移動完了したかのカウント、移動完了は1shotのはずだが２連続回避のため
                    self.plan_completed_cnt += 1
                self.robot_status = 1 # 移動中(ダミー)
                self.plan_2d_status = 0
 
                pass
            elif state == 1:# 移動中
                self.robot_status = 1
                self.plan_2d_status = 1
            elif state == 2: # ローカルモード
                self.robot_status = 2
                self.plan_2d_status = 2
            elif state == 3: # 待機中
                self.robot_status = 1 # 移動中(ダミー)
                self.plan_2d_status = 3
                pass
            elif state == 10: # 非常停止
                self.robot_status = 10
                self.plan_2d_status = 10
            elif state == 11: # ドアオープン
                self.robot_status = 11
                self.plan_2d_status = 11
            elif state == 12: # Lidar検知
                self.robot_status = 12
                self.plan_2d_status = 12
            else:
                self.robot_status = 99
                self.plan_2d_status = 99
                pass
        else:
            # ステータスが変化したか確認
            if state == self.robot_status:
                if len(self.robot_state_len) > 1:
                    if self.robot_state_len[-1] != state:
                        self.robot_state_len.append(state)
                pass
            else:
                # ステータスを一度は送信しているか確認
                if self.robot_state_published == True:
                    self.get_logger().info('Robot State "%d"' %  state)
                    if state == 0:
                        self.robot_status = 0
                    elif state == 1:
                        self.robot_status = 1
                    elif state == 2:
                        self.robot_status = 2
                    elif state == 3:
                        self.robot_status = 3
                    elif state == 10:
                        self.robot_status = 10
                    elif state == 11:
                        self.robot_status = 11
                    elif state == 12:
                        self.robot_status = 12
                    else:
                        self.robot_status = 99
                    # ステータスが変化したフラグを立てる
                    self.robot_state_published = False
                else:
                    if len(self.robot_state_len) == 0:
                        self.robot_state_len.append(state)
                    # lenの最後の状態と違う場合は履歴に追加
                    elif self.robot_state_len[-1] != state:
                        self.robot_state_len.append(state)

                    # まだ一度もPubしていない場合はステータスを更新しない
                    self.get_logger().info('Robot State not updated yet, "%d" -> waiting for first publish. "%d"' %  (self.robot_status,state))
                    

                    pass

        self.get_logger().debug('Current Robot State: "%s"' % self.robot_status)

    # マップIDメッセージコールバック
    def map_callback(self,msg:Int8):
        map_id = msg.data
        #self.get_logger().info('Current Robot Map ID: "%s"' % map_id)
        if map_id == 0:
            self.map_name = "buildingA"
        elif map_id == 1:
            self.map_name = "road"
        elif map_id == 2:
            self.map_name = "buildingB"
        else:
            self.map_name = "Unknown"
        self.get_logger().debug('Current Robot Map Name: "%s"' % self.map_name)

    # ステータスPubタイマーコールバック
    def timer_callback(self):
        latest = True
        if self.status_json is None:
            latest = False
            self.get_logger().info('TF yet.')
        if self.battery_json is None:
            latest = False
            self.get_logger().info('BATTERY yet.')
        if self.robot_status is None:
            latest = False
            self.get_logger().info('STATE yet.')
        if self.map_name is None:
            latest = False
            self.get_logger().info('MAP yet.')

        if latest:
            yaw_degree = self.quaternion_to_euler(
                self.status_json["orientation"]["x"],
                self.status_json["orientation"]["y"],
                self.status_json["orientation"]["z"],
                self.status_json["orientation"]["w"]
            )
            # statusが2の時modeを1にする
            if self.robot_status == 2:
                #ローカルモード
                mode = 1
            else:
                #外部連携モード
                mode = 0
            send_json = {
                "robot_status": {
                    "status": self.robot_status,
                    "mode": mode,
                    "map": self.map_name
                },
                "location": {
                    "x" : self.status_json["position"]["x"],
                    "y" : self.status_json["position"]["y"],
                    "z" : self.status_json["position"]["z"],
                    "t" : yaw_degree

                },
                "battery": {
                    "level": self.battery_json["level"],
                    "power_supply": self.battery_json["power_supply"]

                }
            }
            self.pub.publish(String(data=json.dumps(send_json)))
            self.get_logger().info('Published Robot Status: "%s"' % str(send_json))
            # ステータスを一度Pubしたら状態
            if self.robot_state_published == False:
                if len(self.robot_state_len) > 0:
                    self.get_logger().info('Robot State history published: "%s"' % str(self.robot_state_len))
                    # 先頭を取り出す
                    self.robot_status = self.robot_state_len[0]
                    # 先頭を履歴から削除
                    self.robot_state_len.pop(0)
                    # ステータスが変化したフラグを立てる
                    self.robot_state_published = False
                    
                else:
                    self.robot_state_published = True
        else:
            self.get_logger().info('Data not ready yet.')
            pass

    def quaternion_to_euler(self, x, y, z, w):
        # クオータニオンからオイラー角(ロール、ピッチ、ヨー)に変換したあとヨー角をdegreeに変換して返す
        quat = [x, y, z, w]
        roll, pitch, yaw = tf_transformations.euler_from_quaternion(quat)
        yaw_degree = math.degrees(yaw)
        return yaw_degree
    
    # ステータス確認サービスコールバック
    def srv_status_check_callback(self,request, response):
        # 各コマンドから命令を受け付けられるか問合せが来るので、現在何かを実施中か
        # robotのステータスは待機中かを判断して返す
        try:
            self.get_logger().info('Status Check service called with order_type: %d, current robot_status: %s' % (request.order_type, str(self.robot_status)))
            order_type = request.order_type
            if self.robot_status == 3: #待機中
                if self.use_order_type is None:
                    if order_type != 2: #暫定 初期位置補正以外
                        self.use_order_type = order_type
                        response.response = True
                        response.order_type = self.use_order_type
                        response.response_code = 0
                    else:
                        self.use_order_type = None
                        response.response = True
                        response.order_type = order_type
                        response.response_code = 0
                else:
                    #移動ルート計算中などの命令の隙間時間に別命令が来た場合
                    response.response = False
                    response.order_type = self.use_order_type
                    response.response_code = 4 #別命令実行中
                self.get_logger().info('Response to Status Check srv for order type "%d": response=%s, response_code=%d' % (order_type, str(response.response), response.response_code))
            elif self.robot_status == 1: #移動中
                response.response = False
                if self.use_order_type is None:
                    response.order_type = -1
                else:
                    response.order_type = self.use_order_type
                response.response_code = 4 #別命令実行中
                self.get_logger().info('Robot is currently moving for order type "%d"' % order_type)
            else:
                response.response = False
                if self.use_order_type is None:
                    response.order_type = -1
                else:
                    response.order_type = self.use_order_type
                response.response_code = 10 #ステータス失敗
                self.get_logger().info('Status Check srv: Robot is in abnormal state for order type "%d"' % order_type)

            self.get_logger().info('Returning response: response=%s, response_code=%d' % (str(response.response), response.response_code))
        
        except Exception as e:
            self.get_logger().error('Error in srv_status_check_callback: %s' % str(e))
            response.response = False
            if self.use_order_type is None:
                response.order_type = -1
            else:
                response.order_type = self.use_order_type
            response.response_code = 11 #ステータス監視失敗
        return response
    



def main(args=None):
    rclpy.init(args=args)

    robot_status_node = RobotStatus()

    rclpy.spin(robot_status_node)

    robot_status_node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
        
