#ifndef PLUGININTERFACE__H__
#define PLUGININTERFACE__H__

#include <QObject>
#include <QString>

/**
 * @brief 插件统一接口。
 */
class IPlugin
{
public:
    /**
     * @brief 析构函数。
     */
    virtual ~IPlugin() = default;

    /**
     * @brief 获取插件显示名称。
     * @return 插件名称。
     */
    virtual QString getName() = 0;

    /**
     * @brief 初始化插件。
     * @return true 表示成功；false 表示失败。
     */
    virtual bool init() = 0;

    /**
     * @brief 清理插件。
     * @return true 表示成功；false 表示失败。
     */
    virtual bool clean() = 0;
};

#define IPlugin_iid "lrl.QtPluginsManager.IPlugin"
Q_DECLARE_INTERFACE(IPlugin, IPlugin_iid)

#endif
