/**
 * \file CircularQueue.h
 * \brief 线程安全有界循环队列
 */

#ifndef CIRCULARQUEUE_H
#define CIRCULARQUEUE_H

#include <atomic>
#include <condition_variable>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <utility>

template <typename T>
class CircularQueue
{
public:
    /**
     * @brief 构造函数
     * @param capacity 队列容量，必须大于 0
     */
    explicit CircularQueue(size_t capacity = 1000000)
        : m_buffer(std::make_unique<T[]>(capacity))
        , m_front(0)
        , m_rear(0)
        , m_capacity(capacity)
        , m_size(0)
        , m_stopped(false)
    {
        if (capacity == 0)
        {
            throw std::invalid_argument("Capacity must be greater than 0");
        }
    }

    /**
     * @brief 析构时停止队列并唤醒所有等待线程
     */
    ~CircularQueue()
    {
        stop();
    }

    CircularQueue(const CircularQueue &) = delete;
    CircularQueue & operator=(const CircularQueue &) = delete;

    bool enqueue(const T & value)
    {
        return enqueue_impl(value);
    }

    bool enqueue(T && value)
    {
        return enqueue_impl(std::move(value));
    }

    /**
     * @brief 出队
     * @param value 接收出队元素
     * @return false 代表队列已停止且无可读元素
     */
    bool dequeue(T & value)
    {
        std::unique_lock<std::mutex> lock(m_mtx);
        m_cv.wait(lock, [this] {
            return (m_size.load(std::memory_order_relaxed) > 0) || m_stopped.load(std::memory_order_acquire);
        });

        if (m_stopped.load(std::memory_order_acquire) && (m_size.load(std::memory_order_relaxed) == 0))
        {
            return false;
        }

        value = std::move(m_buffer[m_front]);
        m_front = (m_front + 1) % m_capacity;
        m_size.fetch_sub(1, std::memory_order_relaxed);

        m_cv.notify_one();
        return true;
    }

    /**
     * @brief 停止队列：停止后 enqueue 会失败，dequeue 在队列清空后会返回 false
     */
    void stop()
    {
        std::unique_lock<std::mutex> lock(m_mtx);
        m_stopped.store(true, std::memory_order_release);
        m_cv.notify_all();
    }

    bool isEmpty() const
    {
        return m_size.load(std::memory_order_relaxed) == 0;
    }

    bool isFull() const
    {
        return m_size.load(std::memory_order_relaxed) == m_capacity;
    }

    size_t getSize() const
    {
        return m_size.load(std::memory_order_relaxed);
    }

    bool isStopped() const
    {
        return m_stopped.load(std::memory_order_acquire);
    }

private:
    template <typename U>
    bool enqueue_impl(U && value)
    {
        std::unique_lock<std::mutex> lock(m_mtx);
        m_cv.wait(lock, [this] {
            return m_size.load(std::memory_order_relaxed) < m_capacity || m_stopped.load(std::memory_order_acquire);
        });

        if (m_stopped.load(std::memory_order_acquire))
        {
            return false;
        }

        // m_buffer 为已构造数组，直接赋值即可。
        m_buffer[m_rear] = std::forward<U>(value);
        m_rear = (m_rear + 1) % m_capacity;
        m_size.fetch_add(1, std::memory_order_relaxed);

        m_cv.notify_one();
        return true;
    }

private:
    std::unique_ptr<T[]>    m_buffer;
    size_t                  m_front;
    size_t                  m_rear;
    const size_t            m_capacity;
    std::atomic<size_t>     m_size;
    std::atomic<bool>       m_stopped;
    mutable std::mutex      m_mtx;
    std::condition_variable m_cv;
};

#endif // CIRCULARQUEUE_H
