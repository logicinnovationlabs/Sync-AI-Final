/**
 * Event emitter for pub/sub pattern
 */

class EventEmitter {
  constructor() {
    this.events = new Map();
  }

  on(event, listener) {
    if (!this.events.has(event)) {
      this.events.set(event, []);
    }
    this.events.get(event).push(listener);
    return () => this.off(event, listener);
  }

  once(event, listener) {
    const wrapper = (...args) => {
      listener(...args);
      this.off(event, wrapper);
    };
    this.on(event, wrapper);
  }

  off(event, listener) {
    if (!this.events.has(event)) {
      return;
    }
    const listeners = this.events.get(event);
    const index = listeners.indexOf(listener);
    if (index > -1) {
      listeners.splice(index, 1);
    }
    if (listeners.length === 0) {
      this.events.delete(event);
    }
  }

  emit(event, ...args) {
    if (!this.events.has(event)) {
      return;
    }
    const listeners = this.events.get(event);
    for (const listener of listeners) {
      try {
        listener(...args);
      } catch (error) {
        console.error(`Error in event listener for ${event}:`, error);
      }
    }
  }

  removeAllListeners(event) {
    if (event) {
      this.events.delete(event);
    } else {
      this.events.clear();
    }
  }

  listenerCount(event) {
    return this.events.has(event) ? this.events.get(event).length : 0;
  }

  eventNames() {
    return Array.from(this.events.keys());
  }
}

module.exports = EventEmitter;
