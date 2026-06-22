from rclpy.node import Node
from rclpy.action import ActionServer
from rclpy.action import GoalResponse
import rclpy #ROS2 を Python で開発する場合必須
from rclpy.node import Node #Nodeでやり取りするのに使う？
from custom_msgs.action import Move2D

# ROS2 2D移動アクションサーバー

class Action2DMove:
    def __init__(self, node: Node):
        self.node = node
        self.act_srv = ActionServer(
            node,
            Move2D,
            '/client_api/action/move_2d',
            self._execute_callback,
            goal_callback=self._goal_callback,
        )


    def _goal_callback(self, goal_request):
        self.node.get_logger().info("[Action2DMove]Received 2D Move goal request")
        self.nowid =goal_request.id
        return GoalResponse.ACCEPT
    

    async def _execute_callback(self, goal_handle):
        self.node.get_logger().info("[Action2DMove]Executing 2D Move goal...")
        # ここで2D移動の終了をステータスを管理して待つ処理を実装する
        feedback = Move2D.Feedback()
        result = Move2D.Result()
        resp_int  = 0 # 0:応答(使用しない)　1:成功　2:失敗 ,8:キャンセル
        rimit_cnt = 200  # タイムリミットカウンタ
        rimit_flg = False

        while rclpy.ok():
            # ステータスをチェックして移動完了を確認するロジックをここに追加
            rclpy.spin_once(self.node, timeout_sec=0.5)   # 適切な待機時間を設定

            if self.node.cancel_flag == True:
                #　移動中からキャンセルされた場合の処理
                self.node.get_logger().info("[Action2DMove]Move goal canceled.")
                goal_handle.abort()
                resp_int = 8
                self.node.cancel_flag = False
                break


            if self.node.robot_status == 3: # 待機中
                rimit_cnt -= 1
                if rimit_cnt > 0:
                    self.node.get_logger().debug("[Action2DMove]Waiting for robot to start moving... (rimit_cnt=%d)" % rimit_cnt)
                    feedback.status = 3
                    goal_handle.publish_feedback(feedback)
                else:
                    goal_handle.succeed()
                    resp_int = 1
                    rimit_flg = True
                    break
                pass
            elif self.node.robot_status == 1: #移動中
                rimit_cnt = 200  # タイムリミットカウンタリセット
                feedback.status = 1
                goal_handle.publish_feedback(feedback)
                pass
            elif self.node.robot_status == 0: # 移動完了
                rimit_cnt = 200  # タイムリミットカウンタリセット
                goal_handle.succeed()
                resp_int = 1
                break
            elif self.node.robot_status == 2: # マニュアル走行
                feedback.status = self.node.robot_status
                goal_handle.publish_feedback(feedback)
                pass
            elif self.node.robot_status == 11 or self.node.robot_status == 12: # ドアオープンとLidar検知
                feedback.status = self.node.robot_status
                goal_handle.publish_feedback(feedback)
                pass
            elif self.node.robot_status == 10: # 非常停止
                feedback.status = self.node.robot_status
                goal_handle.publish_feedback(feedback)
                pass
            else:
                # 異常状態の場合の処理
                goal_handle.abort()
                resp_int = 2
                break

        # 実行結果の設定
        result.id = self.nowid
        result.response_code = resp_int

        if rimit_flg == True:
            self.node.get_logger().info("[Action2DMove]rimit flg true")
            if self.node.robot_status == 3: # 待機中
                if self.node.robot_state_published == True:
                    self.node.robot_status = 0
                    self.node.robot_state_published = False #本来同様ロックして送信保証させる
                else:
                    self.node.robot_state_len.append(0)
            rimit_flg = False


        # 次の命令を受け付けられるよう状態を解除
        try:
            self.node.use_order_type = None
        except Exception:
            pass

        if resp_int == 1:
            self.node.get_logger().info("[Action2DMove]2D Move goal completed successfully")
        else:
            self.node.get_logger().info("[Action2DMove]2D Move goal failed with response code: %d" % resp_int)
        return result
    
