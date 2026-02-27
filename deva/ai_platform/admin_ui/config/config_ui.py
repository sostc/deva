"""配置管理UI模块

提供Web界面管理所有配置项，包括：
- 认证配置
- 大模型配置
- 数据库配置
- 钉钉/邮件配置
- 其他系统配置
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


async def render_config_admin(ctx):
    """渲染配置管理页面"""
    await ctx["init_admin_ui"]("配置管理")
    ctx["set_table_style"]()
    ctx["apply_global_styles"]()
    
    ctx["put_markdown"]("## ⚙️ 系统配置管理")
    ctx["put_markdown"]("统一管理所有系统配置，包括认证、大模型、数据库、通知等。所有配置存储在 `NB('deva_config')` 命名空间中。")
    
    tabs = [
        {"title": "🔐 认证配置", "content": _render_auth_config(ctx)},
        {"title": "🤖 大模型配置", "content": _render_llm_config(ctx)},
        {"title": "💾 数据库配置", "content": _render_database_config(ctx)},
        {"title": "📱 通知配置", "content": _render_notification_config(ctx)},
        {"title": "📈 策略配置", "content": _render_strategy_config(ctx)},
        {"title": "📋 全部配置", "content": _render_all_config(ctx)},
    ]
    
    ctx["put_tabs"](tabs)


def _render_auth_config(ctx):
    """渲染认证配置"""
    from deva.config import config
    
    content = []
    
    content.append(ctx["put_markdown"]("### 🔐 认证配置"))
    content.append(ctx["put_markdown"]("管理管理员登录凭证和认证密钥。"))
    
    auth_config = config.get_auth_config()
    
    content.append(ctx["put_input"]("auth_username", type="text", value=auth_config.get("username", ""), placeholder="管理员用户名"))
    content.append(ctx["put_input"]("auth_password", type=ctx["PASSWORD"], value="", placeholder="输入新密码（留空则不修改）"))
    content.append(ctx["put_input"]("auth_password_confirm", type=ctx["PASSWORD"], value="", placeholder="确认新密码"))
    
    content.append(ctx["put_markdown"]("#### 认证密钥"))
    content.append(ctx["put_text"]("认证密钥用于Token签名，自动生成，无需手动设置。"))
    secret = auth_config.get("secret", "")
    if secret:
        masked = secret[:8] + "****" + secret[-8:] if len(secret) > 16 else "****"
        content.append(ctx["put_text"](f"当前密钥: {masked}"))
    
    content.append(ctx["put_button"]("💾 保存认证配置", onclick=lambda: _save_auth_config(ctx), color="primary"))
    content.append(ctx["put_button"]("🔄 重新生成密钥", onclick=lambda: _regenerate_auth_secret(ctx), color="warning"))
    
    return content


def _save_auth_config(ctx):
    """保存认证配置"""
    async def _save():
        from deva.config import config
        
        username = await ctx["pin"].auth_username
        password = await ctx["pin"].auth_password
        password_confirm = await ctx["pin"].auth_password_confirm
        
        if not username or not username.strip():
            ctx["toast"]("用户名不能为空", color="error")
            return
        
        if password:
            if len(password) < 6:
                ctx["toast"]("密码至少6位", color="error")
                return
            if password != password_confirm:
                ctx["toast"]("两次密码不一致", color="error")
                return
            config.set("auth.username", username.strip())
            config.set("auth.password", password)
        else:
            config.set("auth.username", username.strip())
        
        ctx["toast"]("认证配置已保存", color="success")
        ctx["run_js"]("location.reload()")
    
    ctx["run_async"](_save())


def _regenerate_auth_secret(ctx):
    """重新生成认证密钥"""
    async def _regen():
        from deva.config import config
        import secrets
        
        confirm = await ctx["popup"]("确认重新生成认证密钥？", [
            ctx["put_text"]("重新生成后，所有已登录用户需要重新登录。"),
            ctx["put_buttons"]([
                {"label": "确认生成", "value": "confirm"},
                {"label": "取消", "value": "cancel"},
            ], onclick=lambda v: v),
        ])
        
        if confirm == "confirm":
            new_secret = secrets.token_hex(32)
            config.set("auth.secret", new_secret)
            ctx["toast"]("认证密钥已重新生成", color="success")
            ctx["run_js"]("location.reload()")
    
    ctx["run_async"](_regen())


def _render_llm_config(ctx):
    """渲染大模型配置"""
    from deva.config import config, DEFAULT_LLM_CONFIGS
    
    content = []
    
    content.append(ctx["put_markdown"]("### 🤖 大模型配置"))
    content.append(ctx["put_markdown"]("配置大语言模型API，支持DeepSeek、Kimi、SambaNova等。"))
    
    model_types = list(DEFAULT_LLM_CONFIGS.keys())
    
    for model_type in model_types:
        model_config = config.get_llm_config(model_type)
        is_ready = config.is_llm_ready(model_type)
        
        status_text = "✅ 已配置" if is_ready else "⚠️ 未完成配置"
        
        content.append(ctx["put_markdown"](f"#### {model_type.upper()}"))
        content.append(ctx["put_text"](f"状态: {status_text}"))
        
        default_config = DEFAULT_LLM_CONFIGS.get(model_type, {})
        
        content.append(ctx["put_input"](f"llm_{model_type}_api_key", 
                       type=ctx["PASSWORD"], 
                       value="", 
                       placeholder="API密钥（留空则不修改）"))
        content.append(ctx["put_input"](f"llm_{model_type}_base_url", 
                       type="text", 
                       value=model_config.get("base_url", default_config.get("base_url", "")), 
                       placeholder="API基础URL"))
        content.append(ctx["put_input"](f"llm_{model_type}_model", 
                       type="text", 
                       value=model_config.get("model", default_config.get("model", "")), 
                       placeholder="模型名称"))
        
        content.append(ctx["put_button"]("💾 保存", onclick=lambda mt=model_type: _save_llm_config(ctx, mt), color="primary"))
    
    return content


def _save_llm_config(ctx, model_type):
    """保存大模型配置"""
    async def _save():
        from deva.config import config
        
        api_key = await ctx["pin"].__getattr__(f"llm_{model_type}_api_key")
        base_url = await ctx["pin"].__getattr__(f"llm_{model_type}_base_url")
        model = await ctx["pin"].__getattr__(f"llm_{model_type}_model")
        
        if api_key:
            config.set(f"llm.{model_type}.api_key", api_key)
        if base_url:
            config.set(f"llm.{model_type}.base_url", base_url)
        if model:
            config.set(f"llm.{model_type}.model", model)
        
        ctx["toast"](f"{model_type} 配置已保存", color="success")
    
    ctx["run_async"](_save())


def _render_database_config(ctx):
    """渲染数据库配置"""
    from deva.config import config
    
    content = []
    
    content.append(ctx["put_markdown"]("### 💾 数据库配置"))
    content.append(ctx["put_markdown"]("配置SQLite和Redis数据库连接。"))
    
    db_config = config.get_database_config()
    
    content.append(ctx["put_markdown"]("#### SQLite配置"))
    content.append(ctx["put_input"]("db_sqlite_path", type="text", 
                    value=db_config.get("sqlite_path", "~/.deva/nb.sqlite"), 
                    placeholder="SQLite数据库路径"))
    
    content.append(ctx["put_markdown"]("#### Redis配置"))
    content.append(ctx["put_input"]("db_redis_host", type="text", 
                    value=db_config.get("redis_host", "localhost"), 
                    placeholder="Redis主机地址"))
    content.append(ctx["put_input"]("db_redis_port", type="number", 
                    value=str(db_config.get("redis_port", 6379)), 
                    placeholder="Redis端口"))
    content.append(ctx["put_input"]("db_redis_db", type="number", 
                    value=str(db_config.get("redis_db", 0)), 
                    placeholder="Redis数据库编号"))
    content.append(ctx["put_input"]("db_redis_password", type=ctx["PASSWORD"], 
                    value="", 
                    placeholder="Redis密码（留空则不修改）"))
    
    content.append(ctx["put_button"]("💾 保存数据库配置", onclick=lambda: _save_database_config(ctx), color="primary"))
    
    return content


def _save_database_config(ctx):
    """保存数据库配置"""
    async def _save():
        from deva.config import config
        
        sqlite_path = await ctx["pin"].db_sqlite_path
        redis_host = await ctx["pin"].db_redis_host
        redis_port = await ctx["pin"].db_redis_port
        redis_db = await ctx["pin"].db_redis_db
        redis_password = await ctx["pin"].db_redis_password
        
        config.set("database.sqlite_path", sqlite_path)
        config.set("database.redis_host", redis_host)
        config.set("database.redis_port", int(redis_port))
        config.set("database.redis_db", int(redis_db))
        if redis_password:
            config.set("database.redis_password", redis_password)
        
        ctx["toast"]("数据库配置已保存", color="success")
    
    ctx["run_async"](_save())


def _render_notification_config(ctx):
    """渲染通知配置"""
    from deva.config import config
    
    content = []
    
    content.append(ctx["put_markdown"]("### 📱 通知配置"))
    content.append(ctx["put_markdown"]("配置钉钉机器人和邮件通知。"))
    
    content.append(ctx["put_markdown"]("#### 钉钉机器人配置"))
    dtalk_webhook = config.get("dtalk.webhook", "")
    
    content.append(ctx["put_input"]("dtalk_webhook", type="text", 
                    value=dtalk_webhook, 
                    placeholder="钉钉机器人Webhook地址"))
    content.append(ctx["put_input"]("dtalk_secret", type=ctx["PASSWORD"], 
                    value="", 
                    placeholder="钉钉机器人签名密钥（留空则不修改）"))
    
    content.append(ctx["put_markdown"]("#### 邮件配置"))
    mail_hostname = config.get("mail.hostname", "")
    mail_username = config.get("mail.username", "")
    
    content.append(ctx["put_input"]("mail_hostname", type="text", 
                    value=mail_hostname, 
                    placeholder="SMTP服务器地址"))
    content.append(ctx["put_input"]("mail_username", type="text", 
                    value=mail_username, 
                    placeholder="发件人邮箱"))
    content.append(ctx["put_input"]("mail_password", type=ctx["PASSWORD"], 
                    value="", 
                    placeholder="邮箱密码（留空则不修改）"))
    
    content.append(ctx["put_markdown"]("#### Tushare配置"))
    content.append(ctx["put_input"]("tushare_token", type=ctx["PASSWORD"], 
                    value="", 
                    placeholder="Tushare API Token（留空则不修改）"))
    
    content.append(ctx["put_button"]("💾 保存通知配置", onclick=lambda: _save_notification_config(ctx), color="primary"))
    
    return content


def _save_notification_config(ctx):
    """保存通知配置"""
    async def _save():
        from deva.config import config
        
        dtalk_webhook = await ctx["pin"].dtalk_webhook
        dtalk_secret = await ctx["pin"].dtalk_secret
        mail_hostname = await ctx["pin"].mail_hostname
        mail_username = await ctx["pin"].mail_username
        mail_password = await ctx["pin"].mail_password
        tushare_token = await ctx["pin"].tushare_token
        
        config.set("dtalk.webhook", dtalk_webhook)
        if dtalk_secret:
            config.set("dtalk.secret", dtalk_secret)
        
        config.set("mail.hostname", mail_hostname)
        config.set("mail.username", mail_username)
        if mail_password:
            config.set("mail.password", mail_password)
        
        if tushare_token:
            config.set("tushare.token", tushare_token)
        
        ctx["toast"]("通知配置已保存", color="success")
    
    ctx["run_async"](_save())


def _render_all_config(ctx):
    """渲染所有配置"""
    from deva.config import config
    
    content = []
    
    content.append(ctx["put_markdown"]("### 📋 全部配置"))
    content.append(ctx["put_markdown"]("查看所有配置项（敏感信息已遮蔽）。配置存储在 `NB('deva_config')` 命名空间中。"))
    
    content.append(ctx["put_button"]("🔄 刷新", onclick=lambda: ctx["run_js"]("location.reload()"), color="primary"))
    content.append(ctx["put_button"]("🗑️ 清理旧配置命名空间", onclick=lambda: _cleanup_old_namespaces(ctx), color="warning"))
    
    all_config = config.get_all(mask_sensitive=True)
    
    for category, values in all_config.items():
        content.append(ctx["put_markdown"](f"**{category}**"))
        if isinstance(values, dict):
            for key, value in values.items():
                if isinstance(value, dict):
                    for k, v in value.items():
                        content.append(ctx["put_text"](f"  {key}.{k}: {v}"))
                else:
                    content.append(ctx["put_text"](f"  {key}: {values}"))
                break
            else:
                for key, value in values.items():
                    content.append(ctx["put_text"](f"  {key}: {value}"))
    
    return content


def _render_strategy_config(ctx):
    """渲染策略配置"""
    from deva.config import config
    
    content = []
    
    content.append(ctx["put_markdown"]("### 📈 策略配置"))
    content.append(ctx["put_markdown"]("配置策略执行相关参数，包括历史记录保留限制等。"))
    
    max_history_count = config.get("strategy.max_history_count", 300)
    
    content.append(ctx["put_markdown"]("#### 历史记录配置"))
    content.append(ctx["put_input"]("strategy_max_history_count", type="number", 
                    value=str(max_history_count), 
                    placeholder="策略历史记录最大条数"))
    content.append(ctx["put_text"]("注：单个策略的历史记录保留条数不能超过此值。"))
    
    content.append(ctx["put_button"]("💾 保存策略配置", onclick=lambda: _save_strategy_config(ctx), color="primary"))
    
    return content


def _save_strategy_config(ctx):
    """保存策略配置"""
    async def _save():
        from deva.config import config
        
        max_history_count = await ctx["pin"].strategy_max_history_count
        
        try:
            max_history_count = int(max_history_count)
            if max_history_count < 1:
                ctx["toast"]("历史记录最大条数必须大于0", color="error")
                return
            if max_history_count > 1000:
                ctx["toast"]("历史记录最大条数不能超过1000", color="error")
                return
        except ValueError:
            ctx["toast"]("请输入有效的数字", color="error")
            return
        
        config.set("strategy.max_history_count", max_history_count)
        ctx["toast"]("策略配置已保存", color="success")
    
    ctx["run_async"](_save())


def _cleanup_old_namespaces(ctx):
    """清理旧的配置命名空间"""
    async def _cleanup():
        from deva.config import config
        config.cleanup_old_namespaces()
        ctx["toast"]("旧配置命名空间已清理", color="success")
    
    ctx["run_async"](_cleanup())


__all__ = ["render_config_admin"]
