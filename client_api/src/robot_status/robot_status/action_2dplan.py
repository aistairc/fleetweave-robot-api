from rclpy.node import Node
from rclpy.action import ActionServer
from rclpy.action import GoalResponse
import rclpy #ROS2 を Python で開発する場合必須
from rclpy.node import Node #Nodeでやり取りするのに使う？
from custom_msgs.action import Plan2D


# ROS2 2D大局経路アクションサーバー

class Action2DPlan:
    def __init__(self, node: Node):
        self.node = node
        self.act_srv = ActionServer(
            node,
            Plan2D,
            '/client_api/action/plan_2d',
            self._execute_callback,
            goal_callback=self._goal_callback,
        )


    def _goal_callback(self, goal_request):
        self.node.get_logger().info("[Action2DPlan]Received 2D Plan goal request")
        self.nowid =goal_request.id
        # 今回の移動地点（中継地点を含む）の数を保存
        self.point_list = goal_request.move_point_list
        return GoalResponse.ACCEPT
    

    async def _execute_callback(self, goal_handle):
        self.node.get_logger().info("[Action2DPlan]Executing 2D Plan goal...")
        # ここで2D大局経路の終了をステータスを管理して待つ処理を実装する
        feedback = Plan2D.Feedback()
        result = Plan2D.Result()
        resp_int  = 0 # 0:応答(使用しない)　1:成功　2:失敗, 3:中継地点に到達 ,8:キャンセル
        rimit_cnt = 300  # タイムリミットカウンタ

        complete_cnt = 0 #中継地点到着回数
        continue_point = False # 中継地点継続フラグ


        while rclpy.ok():
            # ステータスをチェックして移動完了を確認するロジックをここに追加
            rclpy.spin_once(self.node, timeout_sec=0.1)   # 適切な待機時間を設定
            complete_cnt = self.node.plan_completed_cnt
            # キャンセル割り込み
            if self.node.cancel_flag == True:
                self.node.get_logger().info("[Action2DPlan]Plan goal canceled.")
                goal_handle.abort()
                resp_int = 8
                self.node.cancel_flag = False
                #　割り込み終了てここを停止
                break

            if self.node.plan_2d_status == 3: # 待機中
                # 中継地点に一時的にとどまっているor 移動完了をしているがActionが完了せずにいる
                rimit_cnt -= 1
                if rimit_cnt > 0:
                    # 中継地点は移動中として扱う
                    feedback.status = 3      #本当は待機中
                    feedback.plan_status = 1 #移動中として扱う
                    feedback.move_pont = complete_cnt
                    goal_handle.publish_feedback(feedback)
                    pass
                else:
                    #　移動完了を取得できない時⇒移動完了流して終了
                    # タイマー使って強制完了
                    goal_handle.succeed()
                    resp_int = 1
                    # タイムリミット到達で強制停止
                    break
            elif self.node.plan_2d_status == 1: #移動中
                # 移動中はそのまま移動中
                feedback.status = 1
                feedback.plan_status = 1
                feedback.move_pont = complete_cnt
                goal_handle.publish_feedback(feedback)
                rimit_cnt = 300  # タイムリミットカウンタリセット
                continue_point = True # 中継地点継続フラグセット
                pass
            elif self.node.plan_2d_status == 0: # 移動完了
                #中継地点への到達時は移動中として扱う
                #complete_cnt = self.node.plan_completed_cnt
                rimit_cnt = 300  # タイムリミットカウンタリセット
                # すべての中継地点に到達した場合は完了
                if complete_cnt == self.point_list:
                    goal_handle.succeed()
                    resp_int = 1
                    # 最終到達点に到着した時の完全停止
                    break
                else:
                    if continue_point == True:
                        # 中継地点に到達
                        feedback.status = 0
                        feedback.plan_status = 3 #中継地点到達
                        feedback.move_pont = complete_cnt -1
                        goal_handle.publish_feedback(feedback)
                        continue_point = False # 中継地点継続フラグクリア
                    else:
                        # 中継地点からの再出発
                        feedback.status = 1
                        feedback.plan_status = 1 #移動中として扱う
                        feedback.move_pont = complete_cnt
                        goal_handle.publish_feedback(feedback)
                        pass
                pass
            elif self.node.plan_2d_status == None: #　ステータス更新前
                # ステータスが更新されていない場合の処理
                rimit_cnt -= 1
                if rimit_cnt > 0:
                    self.node.get_logger().info("[Action2DPlan]Waiting for status update...")
                    pass
                else:
                    # タイムリミット到達で強制停止
                    goal_handle.abort()
                    resp_int = 2
                    break
                pass
            elif self.node.plan_2d_status == 2: # マニュアル走行
                # コントローラー操作中
                feedback.status = 2
                feedback.plan_status = 1 #移動中として扱う
                feedback.move_pont = complete_cnt
                goal_handle.publish_feedback(feedback)

            elif self.node.plan_2d_status == 10: # 非常停止
                feedback.status = 10
                feedback.plan_status = 1 #移動中として扱う
                feedback.move_pont = complete_cnt
                goal_handle.publish_feedback(feedback)
            elif self.node.plan_2d_status == 11 or self.node.plan_2d_status == 12: # ドアオープンとLidar検知
                feedback.status = self.node.plan_2d_status
                feedback.plan_status = 1 #移動中として扱う
                feedback.move_pont = complete_cnt
                goal_handle.publish_feedback(feedback)
            else:
                # 異常状態の場合の処理
                goal_handle.abort()
                resp_int = 2
                break


        # 実行結果の設定
        result.id = self.nowid
        result.response_code = resp_int

        # 次の命令を受け付けられるよう状態を解除
        try:
            self.node.use_order_type = None

            if resp_int == 8: #キャンセル時 何もしない
                self.node.robot_status = 3
                self.node.robot_state_published = False #本来同様ロックして送信保証させる
                pass
            elif resp_int == 2: #失敗時 異常状態にしたい
                if self.node.plan_2d_status is not None:
                    self.node.robot_status = self.node.plan_2d_status
                    self.node.robot_state_published = False #本来同様ロックして送信保証させる
                else:
                    self.node.get_logger().error("[Action2DPlan]status not updated on failure cleanup")
                    self.node.robot_status = 3
                    self.node.robot_state_published = False #本来同様ロックして送信保証させる
            else:                #以外は移動完了にしたい
                self.node.robot_status = 0
                self.node.robot_state_published = False #本来同様ロックして送信保証させる
            #self.node.robot_state_published = False #本来同様ロックして送信保証させる

            # リセット
            self.node.plan_completed_cnt = 0 #中継到着回数初期化
            self.node.plan_2d_status = None #大局経路中のステータス初期化
        except Exception:
            pass

        if resp_int == 1:
            self.node.get_logger().info("[Action2DPlan]2D Plan goal completed successfully")
        else:
            self.node.get_logger().info("[Action2DPlan]2D Plan goal failed with response code: %d" % resp_int)
        return result