import paho.mqtt.client as mqtt
from ...settings import MQTT_HOST, MQTT_PORT, MQTT_USERNAME, MQTT_PASSWORD

def create_client(on_message):
    client = mqtt.Client()
    client.on_message = on_message
    
    # 認証情報設定（環境変数で指定されている場合）
    if MQTT_USERNAME and MQTT_PASSWORD:
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    
    client.connect(MQTT_HOST, MQTT_PORT)
    return client
