/**
 * \file	D:\code\git_code\LSkeleton_QT\code\src\Core\LCommon\TSingleton.hpp
 *
 * \brief	Declares the singleton class.
 */

#ifndef TSINGLETON_H
#define TSINGLETON_H

#include <QMutex>
#include <QMutexLocker>

template <class T>

/**
 \class	TSingleton

 \brief	A singleton.

 \author	Lrl
 \date	2026/2/9
 */

class TSingleton
{
public:

    /**
     \fn	static T * TSingleton::getInstance()
    
     \brief	Gets the instance.
    
     \author	Lrl
     \date	2026/2/9
    
     \returns	Null if it fails, else the instance.
     */

    static T * getInstance()
    {
        static T instance;
        return &instance;
    }

protected:

    /**
     \fn	TSingleton::TSingleton() = default;
    
     \brief	Defaulted constructor.
    
     \author	Lrl
     \date	2026/2/9
     */

    TSingleton()  = default;

    /**
     \fn	TSingleton::~TSingleton() = default;
    
     \brief	Defaulted destructor.
    
     \author	Lrl
     \date	2026/2/9
     */

    ~TSingleton() = default;

    /**
     \fn	TSingleton::TSingleton(const TSingleton & parameter1) = delete;
    
     \brief	Deleted copy constructor.
    
     \author	Lrl
     \date	2026/2/9
    
     \param 	parameter1	The first parameter.
     */

    TSingleton(const TSingleton &)             = delete;

    /**
     \fn	TSingleton& TSingleton::operator=(const TSingleton & parameter1) = delete;
    
     \brief	Deleted assignment operator.
    
     \author	Lrl
     \date	2026/2/9
    
     \param 	parameter1	The first parameter.
    
     \returns	A shallow copy of this object.
     */

    TSingleton & operator=(const TSingleton &) = delete;

    /**
     \fn	TSingleton::TSingleton(TSingleton && parameter1) = delete;
    
     \brief	Deleted move constructor.
    
     \author	Lrl
     \date	2026/2/9
    
     \param [in,out]	parameter1	The first parameter.
     */

    TSingleton(TSingleton &&)                  = delete;

    /**
     \fn	TSingleton& TSingleton::operator=(TSingleton && parameter1) = delete;
    
     \brief	Deleted move assignment operator.
    
     \author	Lrl
     \date	2026/2/9
    
     \param [in,out]	parameter1	The first parameter.
    
     \returns	A shallow copy of this object.
     */

    TSingleton & operator=(TSingleton &&)      = delete;
};
#endif // TSINGLETON_H
