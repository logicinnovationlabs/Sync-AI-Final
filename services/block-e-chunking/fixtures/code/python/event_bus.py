from confluent_kafka import Producer, Consumer, KafkaException
from typing import Callable, Optional, Dict, Any
import json
import threading

class EventBus:
    """Manages Kafka event production and consumption."""
    
    def __init__(self, bootstrap_servers: str):
        self.bootstrap_servers = bootstrap_servers
        self.producer_config = {
            'bootstrap.servers': bootstrap_servers,
            'client.id': 'block-e-producer'
        }
        self.consumer_config = {
            'bootstrap.servers': bootstrap_servers,
            'group.id': 'block-e-consumer-group',
            'auto.offset.reset': 'earliest'
        }
        self.producer: Optional[Producer] = None
        self.consumer: Optional[Consumer] = None
    
    def connect_producer(self):
        """Initialize the Kafka producer."""
        self.producer = Producer(self.producer_config)
    
    def connect_consumer(self, topics: list):
        """Initialize the Kafka consumer and subscribe to topics."""
        self.consumer = Consumer(self.consumer_config)
        self.consumer.subscribe(topics)
    
    def publish(self, topic: str, event: Dict[str, Any], key: Optional[str] = None):
        """Publish an event to a Kafka topic."""
        if not self.producer:
            raise RuntimeError("Producer not connected")
        
        value = json.dumps(event).encode('utf-8')
        key_bytes = key.encode('utf-8') if key else None
        
        self.producer.produce(topic, value=value, key=key_bytes, callback=self._delivery_report)
        self.producer.flush()
    
    def consume(self, callback: Callable[[Dict[str, Any]], None], timeout: float = 1.0):
        """Consume events from subscribed topics."""
        if not self.consumer:
            raise RuntimeError("Consumer not connected")
        
        msg = self.consumer.poll(timeout)
        if msg is None:
            return
        if msg.error():
            raise KafkaException(msg.error())
        
        event = json.loads(msg.value().decode('utf-8'))
        callback(event)
    
    def _delivery_report(self, err, msg):
        """Callback for message delivery reports."""
        if err:
            print(f"Message delivery failed: {err}")
        else:
            print(f"Message delivered to {msg.topic()} [{msg.partition()}]")
    
    def close(self):
        """Close producer and consumer connections."""
        if self.producer:
            self.producer.flush()
        if self.consumer:
            self.consumer.close()
