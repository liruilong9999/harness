/**
 * \file	D:\code\git_code\LSkeleton_QT\code\src\App\App1\main.cpp
 *
 * \brief	Implements the main class.
 */

#include <QApplication>
#include <QMenuBar>
#include <PluginManager/PluginManager.h>
#include <QtConcurrent>
#include <QThread>  

/**
 \fn	int main(int argc, char * argv[])

 \brief	Main entry-point for this application.

 \author	Lrl
 \date	2026/2/9

 \param 	argc	The number of command-line arguments provided.
 \param 	argv	An array of command-line argument strings.

 \returns	Exit-code for the process - 0 for success, else an error code.
 */

int main(int argc, char * argv[])
{
    QApplication a(argc, argv); 

    // 获取 IPluginView 实例
    PluginManager::GetInstance().setPluginPath("config");
    PluginManager::GetInstance().loadAllPlugin();
    //LWidget w;
    //w.show();

    int ret = a.exec();
    PluginManager::GetInstance().unloadAllPlugin();

    return ret;
}
