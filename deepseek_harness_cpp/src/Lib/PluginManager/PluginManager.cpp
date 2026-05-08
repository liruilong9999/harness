#include "PluginManager.h"

#include <LCommon/IPlugin.h>

#include <QCoreApplication>
#include <QDebug>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QFileInfoList>
#include <QJsonArray>
#include <QJsonObject>
#include <QPluginLoader>
#include <QSet>
#include <QVariantList>
#include <QXmlStreamReader>

namespace {
const char * const kModuleTag = "[PluginManager]";
const QString kPluginConfigPath = QStringLiteral("config/config.xml");
const QString kPluginConfigBasePath = QStringLiteral("config/");
const QString kPluginDirName = QStringLiteral("plugin");
const QString kPluginElementName = QStringLiteral("plugin");
const QString kEnabledValue = QStringLiteral("1");
} // namespace

struct PluginConfigInfo
{
    QString pluginName;
    QString pluginPath;
    QString isUsed{kEnabledValue};
};

class PluginManagerPrivate
{
public:
    bool check(const QString & filePath)
    {
        QSet<QString> visiting;
        return check(filePath, visiting);
    }

    bool check(const QString & filePath, QSet<QString> & visiting)
    {
        if (true == visiting.contains(filePath))
        {
            qWarning() << kModuleTag << "检测到循环依赖:" << filePath;
            return false;
        }

        visiting.insert(filePath);
        const QVariantList dependencies = m_dependencies.value(filePath);
        for (const QVariant & item : dependencies)
        {
            const QVariantMap dependencyMap = item.toMap();
            const QVariant dependencyName = dependencyMap.value(QStringLiteral("name"));
            const QVariant dependencyVersion = dependencyMap.value(QStringLiteral("version"));

            if (false == m_names.values().contains(dependencyName))
            {
                qWarning() << kModuleTag << "缺少依赖:"
                           << dependencyName.toString()
                           << "插件 =" << filePath;
                visiting.remove(filePath);
                return false;
            }

            const QString dependencyPath = m_names.key(dependencyName);
            if (m_versions.value(dependencyPath) != dependencyVersion)
            {
                qWarning() << kModuleTag << "依赖版本不匹配:"
                           << dependencyName.toString()
                           << "需要 =" << dependencyVersion.toString()
                           << "当前 =" << m_versions.value(dependencyPath).toString();
                visiting.remove(filePath);
                return false;
            }

            if (false == check(dependencyPath, visiting))
            {
                qWarning() << kModuleTag << "依赖链检查失败:" << filePath;
                visiting.remove(filePath);
                return false;
            }
        }

        visiting.remove(filePath);
        return true;
    }

    QHash<QString, QVariant>         m_names;
    QHash<QString, QVariant>         m_versions;
    QHash<QString, QVariantList>     m_dependencies;
    QHash<QString, QPluginLoader *>  m_loaders;
    QHash<QString, PluginConfigInfo> m_pluginConfigInfo;
    QStringList                      m_loadOrder;
};

PluginManager & PluginManager::GetInstance()
{
    static PluginManager instance;
    return instance;
}

void PluginManager::setPluginPath(const QString & path, bool isFullPath)
{
    if (true == isFullPath)
    {
        m_configFile = path;
        return;
    }

    m_configFile = QDir(qApp->applicationDirPath()).filePath(kPluginConfigBasePath + path + QStringLiteral(".xml"));
}

bool PluginManager::loadPlugin(const QString & filePath)
{
    if (nullptr == m_pluginData)
    {
        qWarning() << kModuleTag << "加载插件失败: m_pluginData 为空";
        return false;
    }

    if (false == QLibrary::isLibrary(filePath))
    {
        qWarning() << kModuleTag << "加载插件失败: 不是动态库" << filePath;
        return false;
    }

    if (true == m_pluginData->m_loaders.contains(filePath))
    {
        return true;
    }

    if (false == m_pluginData->check(filePath))
    {
        qWarning() << kModuleTag << "加载插件失败: 依赖检查未通过" << filePath;
        return false;
    }

    QPluginLoader * const pLoader = new QPluginLoader(filePath);
    const QString fileName = QFileInfo(filePath).fileName();
    if (false == pLoader->load())
    {
        qWarning() << kModuleTag << "加载插件失败:" << fileName << pLoader->errorString();
        delete pLoader;
        return false;
    }

    IPlugin * const pPlugin = qobject_cast<IPlugin *>(pLoader->instance());
    if (nullptr == pPlugin)
    {
        qWarning() << kModuleTag << "加载插件失败: 未实现 IPlugin 接口" << fileName;
        pLoader->unload();
        delete pLoader;
        return false;
    }

    m_pluginData->m_loaders.insert(filePath, pLoader);
    qInfo() << kModuleTag << "加载插件成功:" << fileName;
    return true;
}

bool PluginManager::unloadPlugin(const QString & filePath)
{
    if (nullptr == m_pluginData)
    {
        qWarning() << kModuleTag << "卸载插件失败: m_pluginData 为空";
        return false;
    }

    QPluginLoader * const pLoader = m_pluginData->m_loaders.value(filePath, nullptr);
    if (nullptr == pLoader)
    {
        qWarning() << kModuleTag << "卸载插件失败: 未找到 loader" << filePath;
        return false;
    }

    const QString fileName = QFileInfo(filePath).fileName();
    if (false == pLoader->unload())
    {
        qWarning() << kModuleTag << "卸载插件失败:" << fileName << pLoader->errorString();
        return false;
    }

    m_pluginData->m_loaders.remove(filePath);
    delete pLoader;
    qInfo() << kModuleTag << "卸载插件成功:" << fileName;
    return true;
}

bool PluginManager::loadAllPlugin()
{
    if (nullptr == m_pluginData)
    {
        qWarning() << kModuleTag << "批量加载失败: m_pluginData 为空";
        return false;
    }

    unloadAllPlugin();
    setPluginList();
    m_pluginData->m_names.clear();
    m_pluginData->m_versions.clear();
    m_pluginData->m_dependencies.clear();

    QDir pluginsDir(qApp->applicationDirPath());
    if (false == pluginsDir.cd(kPluginDirName))
    {
        qWarning() << kModuleTag << "插件目录不存在:" << pluginsDir.filePath(kPluginDirName);
        return false;
    }

    const QFileInfoList pluginInfoList = pluginsDir.entryInfoList(QDir::Files | QDir::NoDotAndDotDot);
    QFileInfoList usableList;
    for (const QFileInfo & fileInfo : pluginInfoList)
    {
        const QString absoluteFilePath = fileInfo.absoluteFilePath();
        if (false == QLibrary::isLibrary(absoluteFilePath))
        {
            continue;
        }

        const QString pluginKey = fileInfo.baseName();
        if (false == m_pluginData->m_pluginConfigInfo.contains(pluginKey))
        {
            continue;
        }

        const PluginConfigInfo config = m_pluginData->m_pluginConfigInfo.value(pluginKey);
        if (kEnabledValue == config.isUsed)
        {
            usableList.push_back(fileInfo);
            scanMetaData(absoluteFilePath);
        }
    }

    bool allLoaded = true;
    for (const QString & pluginName : m_pluginData->m_loadOrder)
    {
        bool foundAndLoaded = false;
        for (const QFileInfo & fileInfo : usableList)
        {
            if (fileInfo.baseName() != pluginName)
            {
                continue;
            }

            foundAndLoaded = loadPlugin(fileInfo.absoluteFilePath());
            if (false == foundAndLoaded)
            {
                allLoaded = false;
            }
            break;
        }

        if (false == foundAndLoaded)
        {
            qWarning() << kModuleTag << "未找到可加载插件:" << pluginName;
            allLoaded = false;
        }
    }

    for (const QString & pluginName : m_pluginData->m_loadOrder)
    {
        for (const QFileInfo & fileInfo : usableList)
        {
            if (fileInfo.baseName() != pluginName)
            {
                continue;
            }

            const QString absoluteFilePath = fileInfo.absoluteFilePath();
            QPluginLoader * const pLoader = m_pluginData->m_loaders.value(absoluteFilePath, nullptr);
            if (nullptr == pLoader)
            {
                qWarning() << kModuleTag << "初始化插件失败: loader 为空" << pluginName;
                allLoaded = false;
                break;
            }

            IPlugin * const pPlugin = qobject_cast<IPlugin *>(pLoader->instance());
            if (nullptr == pPlugin)
            {
                qWarning() << kModuleTag << "初始化插件失败: 插件实例转换失败" << pluginName;
                allLoaded = false;
                break;
            }

            if (true == pPlugin->init())
            {
                qInfo() << kModuleTag << "初始化插件成功:" << pluginName;
            }
            else
            {
                qWarning() << kModuleTag << "初始化插件失败:" << pluginName;
                allLoaded = false;
            }
            break;
        }
    }

    return allLoaded;
}

bool PluginManager::unloadAllPlugin()
{
    if (nullptr == m_pluginData)
    {
        qWarning() << kModuleTag << "批量卸载失败: m_pluginData 为空";
        return false;
    }

    bool allUnloaded = true;
    for (int i = m_pluginData->m_loadOrder.size() - 1; i >= 0; --i)
    {
        const QString pluginName = m_pluginData->m_loadOrder.at(i);
        for (const QString & path : m_pluginData->m_loaders.keys())
        {
            const QFileInfo fileInfo(path);
            if (fileInfo.baseName() != pluginName)
            {
                continue;
            }

            QPluginLoader * const pLoader = m_pluginData->m_loaders.value(path, nullptr);
            if (nullptr == pLoader)
            {
                qWarning() << kModuleTag << "清理插件失败: loader 为空" << pluginName;
                allUnloaded = false;
                break;
            }

            IPlugin * const pPlugin = qobject_cast<IPlugin *>(pLoader->instance());
            if ((nullptr != pPlugin) && (false == pPlugin->clean()))
            {
                qWarning() << kModuleTag << "清理插件失败:" << pluginName;
                allUnloaded = false;
            }
            break;
        }
    }

    for (int i = m_pluginData->m_loadOrder.size() - 1; i >= 0; --i)
    {
        const QString pluginName = m_pluginData->m_loadOrder.at(i);
        for (const QString & path : m_pluginData->m_loaders.keys())
        {
            const QFileInfo fileInfo(path);
            if (fileInfo.baseName() != pluginName)
            {
                continue;
            }

            if (false == unloadPlugin(path))
            {
                allUnloaded = false;
            }
            break;
        }
    }

    if (false == m_pluginData->m_loaders.isEmpty())
    {
        for (QPluginLoader * pLoader : m_pluginData->m_loaders)
        {
            if (nullptr == pLoader)
            {
                continue;
            }

            pLoader->unload();
            delete pLoader;
        }
        m_pluginData->m_loaders.clear();
        allUnloaded = false;
    }

    return allUnloaded;
}

QList<QString> PluginManager::getPluginsName()
{
    if (nullptr == m_pluginData)
    {
        return {};
    }

    return m_pluginData->m_loadOrder;
}

void PluginManager::scanMetaData(const QString & filePath)
{
    if (nullptr == m_pluginData)
    {
        qWarning() << kModuleTag << "扫描元数据失败: m_pluginData 为空";
        return;
    }

    if (false == QLibrary::isLibrary(filePath))
    {
        qWarning() << kModuleTag << "扫描元数据失败: 非动态库" << filePath;
        return;
    }

    QPluginLoader loader(filePath);
    const QJsonObject json = loader.metaData().value(QStringLiteral("MetaData")).toObject();
    if (true == json.isEmpty())
    {
        qWarning() << kModuleTag << "扫描元数据失败: MetaData 为空" << filePath;
        return;
    }

    m_pluginData->m_names.insert(filePath, json.value(QStringLiteral("name")).toVariant());
    m_pluginData->m_versions.insert(filePath, json.value(QStringLiteral("version")).toVariant());
    m_pluginData->m_dependencies.insert(
        filePath,
        json.value(QStringLiteral("dependencies")).toArray().toVariantList());
}

void PluginManager::setPluginList()
{
    if (nullptr == m_pluginData)
    {
        qWarning() << kModuleTag << "设置插件列表失败: m_pluginData 为空";
        return;
    }

    if (true == m_configFile.isEmpty())
    {
        m_configFile = QDir(qApp->applicationDirPath()).filePath(kPluginConfigPath);
    }

    m_pluginData->m_pluginConfigInfo.clear();
    m_pluginData->m_loadOrder.clear();

    QFile file(m_configFile);
    if (false == file.open(QIODevice::ReadOnly | QIODevice::Text))
    {
        qWarning() << kModuleTag << "打开插件配置失败:" << m_configFile;
        return;
    }

    qInfo() << kModuleTag << "读取插件配置成功:" << m_configFile;
    QXmlStreamReader xml(&file);
    while ((false == xml.atEnd()) && (false == xml.hasError()))
    {
        const QXmlStreamReader::TokenType token = xml.readNext();
        if (QXmlStreamReader::StartElement != token)
        {
            continue;
        }

        if (kPluginElementName != xml.name())
        {
            continue;
        }

        const QXmlStreamAttributes attributes = xml.attributes();
        const QString name = attributes.value(QStringLiteral("name")).toString();
        QString path = attributes.value(QStringLiteral("path")).toString();
        const QString isUsed = attributes.value(QStringLiteral("isUsed")).toString();

#ifdef _DEBUG
        path += QStringLiteral("d");
#endif

        PluginConfigInfo info;
        info.pluginName = name;
        info.pluginPath = path;
        info.isUsed = isUsed;

        if (kEnabledValue == info.isUsed)
        {
            m_pluginData->m_pluginConfigInfo.insert(info.pluginPath, info);
            m_pluginData->m_loadOrder.append(info.pluginPath);
        }
    }

    if (true == xml.hasError())
    {
        qWarning() << kModuleTag << "解析插件配置失败:" << xml.errorString();
    }
}

PluginManager::PluginManager()
    : m_pluginData(new PluginManagerPrivate)
{
}

PluginManager::~PluginManager()
{
    if (nullptr != m_pluginData)
    {
        unloadAllPlugin();
        delete m_pluginData;
        m_pluginData = nullptr;
    }
}
