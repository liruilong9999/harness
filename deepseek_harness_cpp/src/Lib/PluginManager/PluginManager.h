#ifndef PLUGINMANAGER_H__
#define PLUGINMANAGER_H__

#include "PluginManager_Gloabal.h"

#include <QList>
#include <QObject>
#include <QString>

class PluginManagerPrivate;

/**
 * @brief 插件管理器。
 */
class PLUGINSMANAGERSHARED_EXPORT PluginManager : public QObject
{
    Q_OBJECT
public:
    /**
     * @brief 获取插件管理器单例。
     * @return 插件管理器实例。
     */
    static PluginManager & GetInstance();

    /**
     * @brief 设置插件配置路径。
     * @param path 配置文件路径或相对配置名。
     * @param isFullPath `true` 表示 `path` 为完整路径。
     */
    void setPluginPath(const QString & path, bool isFullPath = false);

    /**
     * @brief 加载单个插件。
     * @param filePath 插件文件完整路径。
     * @return true 表示成功；false 表示失败。
     */
    bool loadPlugin(const QString & filePath);

    /**
     * @brief 卸载单个插件。
     * @param filePath 插件文件完整路径。
     * @return true 表示成功；false 表示失败。
     */
    bool unloadPlugin(const QString & filePath);

    /**
     * @brief 加载全部插件。
     * @return true 表示全部成功；false 表示存在失败。
     */
    bool loadAllPlugin();

    /**
     * @brief 卸载全部插件。
     * @return true 表示全部成功；false 表示存在失败。
     */
    bool unloadAllPlugin();

    /**
     * @brief 获取插件加载顺序。
     * @return 插件名称列表。
     */
    QList<QString> getPluginsName();

    /**
     * @brief 扫描插件元数据。
     * @param filepath 插件文件路径。
     */
    void scanMetaData(const QString & filepath);

    /**
     * @brief 读取插件配置并建立加载列表。
     */
    void setPluginList();

private:
    /**
     * @brief 构造函数。
     */
    PluginManager();

    /**
     * @brief 析构函数。
     */
    ~PluginManager();

private:
    QString               m_configFile;
    PluginManagerPrivate * m_pluginData{nullptr};
};

#endif
