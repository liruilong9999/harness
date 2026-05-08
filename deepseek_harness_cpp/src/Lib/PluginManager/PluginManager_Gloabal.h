/**
 * \file	D:\code\git_code\LSkeleton_QT\code\src\Core\PluginManager\PluginManager_Gloabal.h
 *
 * \brief	Declares the plugin manager gloabal class.
 */

#ifndef PLUGINMANAGER_GLOBAL_H
#define PLUGINMANAGER_GLOBAL_H

#include <QtCore/qglobal.h>

#if defined(PLUGINSMANAGER_LIBRARY)

/**
 \def	PLUGINSMANAGERSHARED_EXPORT

 \brief	A macro that defines pluginsmanagershared export.

 \author	Lrl
 \date	2026/2/9
 */

#define PLUGINSMANAGERSHARED_EXPORT Q_DECL_EXPORT
#else

/**
 \def	PLUGINSMANAGERSHARED_EXPORT

 \brief	A macro that defines pluginsmanagershared export.

 \author	Lrl
 \date	2026/2/9
 */

#define PLUGINSMANAGERSHARED_EXPORT Q_DECL_IMPORT
#endif

#endif
