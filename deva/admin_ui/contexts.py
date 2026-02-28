"""Context builders for admin route wrappers."""

from .menus import create_nav_menu, create_sidebar, init_floating_menu_manager
from .utils import stable_widget_id


SSE_LOG_JS = r'''
// 确保DOM元素存在
function ensureElementReady(selector, callback) {
    let checkCount = 0;
    const maxChecks = 100; // 最多检查10秒
    const checkExist = setInterval(function() {
        checkCount++;
        const element = document.querySelector(selector);
        if (element) {
            clearInterval(checkExist);
            callback(element);
        } else if (checkCount >= maxChecks) {
            clearInterval(checkExist);
            console.warn('等待元素超时:', selector);
        }
    }, 100);
}

// 清理现有的SSE连接
if (window.sseConnection) {
    try {
        window.sseConnection.close();
    } catch (e) {
        console.warn('关闭现有SSE连接时出错:', e);
    }
    window.sseConnection = null;
}

// 创建新的SSE连接
function createSSEConnection() {
    try {
        window.sseConnection = new EventSource('/logsse');
        console.log('SSE连接已创建');
        
        window.sseConnection.onopen = function() {
            console.log('SSE连接已打开，等待消息...');
        };
        
        window.sseConnection.onmessage = function(event) {
            try {
                const data = JSON.parse(event.data);
                const message = data.message || data;
                const logEntry = `${new Date().toLocaleTimeString()} - ${message}\n`;
                
                // 更新首页日志框
                const mainLogbox = document.querySelector("#webio-logbox-log");
                if (mainLogbox) {
                    mainLogbox.textContent += logEntry;
                    mainLogbox.scrollTop = mainLogbox.scrollHeight;
                }
                
                // 更新 sidebar 日志框
                const sidebarLogbox = document.querySelector("#webio-logbox-sidebar_log");
                if (sidebarLogbox) {
                    sidebarLogbox.textContent += logEntry;
                    sidebarLogbox.scrollTop = sidebarLogbox.scrollHeight;
                }
                
                // 滚动 sidebar 容器
                const messageList = document.querySelector('#webio-scope-sidebar');
                if (messageList) {
                    messageList.scrollTop = messageList.scrollHeight;
                }
            } catch (error) {
                console.error('处理SSE消息时出错:', error);
            }
        };
        
        window.sseConnection.onerror = function(error) {
            console.error('SSE连接出错:', error);
            if (window.sseConnection) {
                try {
                    window.sseConnection.close();
                } catch (e) {
                    console.warn('关闭SSE连接时出错:', e);
                }
                window.sseConnection = null;
            }
            
            // 如果页面正在跳转，不再重连
            if (window.__pageNavigating) {
                console.log('页面正在跳转，停止重连');
                return;
            }
            
            // 延迟重新连接
            setTimeout(() => {
                // 再次检查页面是否正在跳转
                if (!window.__pageNavigating && !window.sseConnection) {
                    console.log('尝试重新建立SSE连接...');
                    createSSEConnection();
                }
            }, 5000);
        };
        
    } catch (e) {
        console.error('创建SSE连接失败:', e);
        window.sseConnection = null;
    }
}

// 页面跳转标记
window.__pageNavigating = false;

// 页面卸载时清理连接
window.addEventListener('beforeunload', function() {
    if (window.sseConnection) {
        try {
            window.sseConnection.close();
        } catch (e) {
            console.warn('页面卸载时关闭SSE连接出错:', e);
        }
        window.sseConnection = null;
    }
    window.__pageNavigating = true;
});

// 启动SSE连接
createSSEConnection();

console.log('SSE脚本已加载');
console.log('当前页面URL:', window.location.href);
console.log('SSE连接URL:', '/logsse');
'''


def tasks_ctx(ns):
    return {
        'NB': ns['NB'],
        'tasks': ns['tasks'],
        'scheduler': ns['scheduler'],
        'log': ns['log'],
        'toast': ns['toast'],
        'run_js': ns['run_js'],
        'input_group': ns['input_group'],
        'input': ns['input'],
        'textarea': ns['textarea'],
        'select': ns['select'],
        'TEXT': ns['TEXT'],
        'async_gpt': ns['async_gpt'],
        'get_gpt_response': ns['get_gpt_response'],
        'use_scope': ns['use_scope'],
        'put_text': ns['put_text'],
        'put_markdown': ns['put_markdown'],
        'put_code': ns['put_code'],
        'put_table': ns['put_table'],
        'put_button': ns['put_button'],
        'put_row': ns['put_row'],
        'put_collapse': ns['put_collapse'],
        'popup': ns['popup'],
        'close_popup': ns['close_popup'],
        'actions': ns['actions'],
        'put_html': ns['put_html'],
        'file_upload': ns.get('file_upload'),
        'radio': ns.get('radio'),
        'checkbox': ns.get('checkbox'),
        'stop_task': ns['stop_task'],
        'start_task': ns['start_task'],
        'delete_task': ns['delete_task'],
        'recover_task': ns['recover_task'],
        'remove_task_forever': ns['remove_task_forever'],
        'manage_tasks': ns['manage_tasks'],
        'global_ns': ns,
    }


def document_ui_ctx(ns):
    return {
        'cache': ns['_DOCUMENT_CACHE'],
        'cache_ttl': ns['_DOCUMENT_CACHE_TTL'],
        'warn': ns['warn'],
        'put_text': ns['put_text'],
        'put_button': ns['put_button'],
        'put_table': ns['put_table'],
        'put_row': ns['put_row'],
        'put_tabs': ns['put_tabs'],
        'run_async': ns['run_async'],
        'inspect_object': ns['inspect_object'],
        'run_object_smoke_test': ns['_run_object_smoke_test'],
        'document': ns['document'],
        'popup': ns['popup'],
        'put_markdown': ns['put_markdown'],
        'put_html': ns['put_html'],
        'extract_doc_examples': ns['_extract_doc_examples'],
        'mask_attr_value': ns['_mask_attr_value'],
    }


def tables_ctx(ns, admin_tables):
    return {
        'NB': ns['NB'],
        'ls': ns['ls'],
        'sample': ns['sample'],
        'pd': ns['pd'],
        'pin': ns['pin'],
        'clear': ns['clear'],
        'warn': ns['warn'],
        'toast': ns['toast'],
        'popup': ns['popup'],
        'close_popup': ns['close_popup'],
        'input_group': ns['input_group'],
        'input': ns['input'],
        'textarea': ns['textarea'],
        'put_markdown': ns['put_markdown'],
        'put_row': ns['put_row'],
        'put_table': ns['put_table'],
        'put_text': ns['put_text'],
        'put_button': ns['put_button'],
        'put_buttons': ns['put_buttons'],
        'put_collapse': ns['put_collapse'],
        'put_datatable': ns['put_datatable'],
        'put_file_upload': ns['put_file_upload'],
        'put_input': ns['put_input'],
        'use_scope': ns['use_scope'],
        'run_async': ns['run_async'],
        'traceback': ns['traceback'],
        'log': ns['log'],
        'datetime': ns['datetime'],
        'table_click': ns['table_click'],
        'delete_table': ns['delete_table'],
        'create_new_table': ns['create_new_table'],
        'refresh_table_display': ns['refresh_table_display'],
    }


def main_ui_ctx(ns, admin_tables):
    return {
        'NB': ns['NB'],
        'browser': ns['browser'],
        'tabs': ns['tabs'],
        'tab': ns['tab'],
        'first': ns['first'],
        'Stream': ns['Stream'],
        'timer': ns['timer'],
        'NS': ns['NS'],
        'log': ns['log'],
        'ls': ns['ls'],
        'print': ns['print'],
        'Dtalk': ns['Dtalk'],
        'pin': ns['pin'],
        'asyncio': ns['asyncio'],
        'requests': ns['requests'],
        'json': ns['json'],
        'TEXT': ns['TEXT'],
        'actions': ns['actions'],
        'input': ns['input'],
        'input_group': ns['input_group'],
        'textarea': ns['textarea'],
        'select': ns['select'],
        'radio': ns['radio'],
        'checkbox': ns['checkbox'],
        'run_js': ns['run_js'],
        'run_async': ns['run_async'],
        'run_asyncio_coroutine': ns['run_asyncio_coroutine'],
        'get_session_implement': ns['get_session_implement'],
        'set_env': ns['set_env'],
        'setup_admin_runtime': ns['setup_admin_runtime'],
        'basic_auth': ns['basic_auth'],
        'get_gpt_response': ns['get_gpt_response'],
        'put_out': ns['put_out'],
        'put_link': ns['put_link'],
        'put_text': ns['put_text'],
        'put_markdown': ns['put_markdown'],
        'put_table': ns['put_table'],
        'put_row': ns['put_row'],
        'put_html': ns['put_html'],
        'put_tabs': ns['put_tabs'],
        'put_button': ns['put_button'],
        'put_buttons': ns['put_buttons'],
        'put_collapse': ns['put_collapse'],
        'put_input': ns['put_input'],
        'put_logbox': ns['put_logbox'],
        'put_code': ns['put_code'],
        'logbox_append': ns['logbox_append'],
        'set_scope': ns['set_scope'],
        'use_scope': ns['use_scope'],
        'clear': ns['clear'],
        'popup': ns['popup'],
        'toast': ns['toast'],
        'PASSWORD': ns['PASSWORD'],
        'datetime': ns['datetime'],
        'stable_widget_id': stable_widget_id,
        'edit_data_popup': ns['edit_data_popup'],
        'write_to_log': ns['write_to_log'],
        'show_timer_detail': ns['show_timer_detail'],
        'sse_js': SSE_LOG_JS,
        'init_admin_ui': ns['init_admin_ui'],
        'view_tab': ns['view_tab'],
        'close_tab': ns['close_tab'],
        'open_new_tab': ns['open_new_tab'],
        'show_browser_status': ns['show_browser_status'],
        'dynamic_popup': ns['dynamic_popup'],
        'summarize_tabs': ns['summarize_tabs'],
        'async_json_gpt': ns['async_json_gpt'],
        'extract_important_links': ns['extract_important_links'],
        'truncate': ns['truncate'],
        'set_table_style': ns['set_table_style'],
        'apply_global_styles': ns['apply_global_styles'],
        'process_tabs': ns['process_tabs'],
        'extended_reading': ns['extended_reading'],
        'close_all_tabs': ns['close_all_tabs'],
        'show_dtalk_archive': ns['show_dtalk_archive'],
        'view_dtalk_message': ns['view_dtalk_message'],
        'delete_dtalk_message': ns['delete_dtalk_message'],
        'clear_all_dtalk_messages': ns['clear_all_dtalk_messages'],
        'init_floating_menu_manager': init_floating_menu_manager,
        'create_sidebar': create_sidebar,
        'create_nav_menu': create_nav_menu,
        'run_ai_in_worker': ns['run_ai_in_worker'],
        'get_bus_runtime_status': ns['get_bus_runtime_status'],
        'get_bus_clients': ns['get_bus_clients'],
        'get_bus_recent_messages': ns['get_bus_recent_messages'],
        'send_bus_message': ns['send_bus_message'],
    }


def strategy_ctx(ns):
    return {
        'init_admin_ui': ns['init_admin_ui'],
        'get_strategy_config': ns.get('get_strategy_config'),
        'set_strategy_config': ns.get('set_strategy_config'),
        'get_strategy_basic_meta': ns.get('get_strategy_basic_meta'),
        'refresh_strategy_basic_df': ns.get('refresh_strategy_basic_df'),
        'refresh_strategy_basic_df_async': ns.get('refresh_strategy_basic_df_async'),


        'put_markdown': ns['put_markdown'],
        'put_text': ns['put_text'],
        'put_table': ns['put_table'],
        'put_row': ns['put_row'],
        'put_button': ns['put_button'],
        'put_buttons': ns['put_buttons'],
        'put_html': ns['put_html'],
        'put_collapse': ns['put_collapse'],
        'set_scope': ns['set_scope'],
        'use_scope': ns['use_scope'],
        'run_async': ns['run_async'],
        'run_js': ns['run_js'],
        'toast': ns['toast'],
        'NS': ns['NS'],
        'NB': ns['NB'],
        'input_group': ns['input_group'],
        'input': ns['input'],
        'textarea': ns['textarea'],
        'select': ns['select'],
        'radio': ns['radio'],
        'checkbox': ns['checkbox'],
        'NUMBER': ns['NUMBER'],
        'popup': ns['popup'],
        'close_popup': ns['close_popup'],
        'put_code': ns['put_code'],
        'actions': ns['actions'],
        'warn': ns['warn'],
        'log': ns['log'],
        'requests': ns['requests'],
        'AsyncOpenAI': ns['AsyncOpenAI'],
        'put_out': ns['put_out'],
        'get_gpt_response': ns['get_gpt_response'],
        'run_ai_in_worker': ns['run_ai_in_worker'],
        'traceback': ns['traceback'],
    }


def datasource_ctx(ns):
    return {
        'init_admin_ui': ns['init_admin_ui'],
        'put_markdown': ns['put_markdown'],
        'put_text': ns['put_text'],
        'put_table': ns['put_table'],
        'put_row': ns['put_row'],
        'put_button': ns['put_button'],
        'put_buttons': ns['put_buttons'],
        'put_html': ns['put_html'],
        'put_collapse': ns['put_collapse'],
        'set_scope': ns['set_scope'],
        'use_scope': ns['use_scope'],
        'run_async': ns['run_async'],
        'run_js': ns['run_js'],
        'toast': ns['toast'],
        'NS': ns['NS'],
        'NB': ns['NB'],
        'input_group': ns['input_group'],
        'input': ns['input'],
        'textarea': ns['textarea'],
        'select': ns['select'],
        'NUMBER': ns['NUMBER'],
        'popup': ns['popup'],
        'close_popup': ns['close_popup'],
        'actions': ns['actions'],
        'put_code': ns['put_code'],
        'warn': ns['warn'],
        'log': ns['log'],
        'requests': ns['requests'],
        'AsyncOpenAI': ns['AsyncOpenAI'],
        'put_out': ns['put_out'],
        'get_gpt_response': ns['get_gpt_response'],
        'run_ai_in_worker': ns['run_ai_in_worker'],
        'traceback': ns['traceback'],
        'asyncio': ns['asyncio'],
    }


def monitor_ui_ctx(ns):
    return {
        'init_admin_ui': ns['init_admin_ui'],
        'NB': ns['NB'],
        'Stream': ns['Stream'],
        'sample': ns['sample'],
        'log': ns['log'],
        'global_ns': ns,
        'pin': ns['pin'],
        'put_markdown': ns['put_markdown'],
        'put_text': ns['put_text'],
        'put_table': ns['put_table'],
        'put_row': ns['put_row'],
        'put_button': ns['put_button'],
        'put_buttons': ns['put_buttons'],
        'put_html': ns['put_html'],
        'put_input': ns['put_input'],
        'put_code': ns['put_code'],
        'set_scope': ns['set_scope'],
        'use_scope': ns['use_scope'],
        'clear': ns['clear'],
        'run_async': ns['run_async'],
        'toast': ns['toast'],
        'popup': ns['popup'],
    }


def follow_ui_ctx(ns, admin_tables):
    return {
        'init_admin_ui': ns['init_admin_ui'],
        'NB': ns['NB'],
        'log': ns['log'],
        'pin': ns['pin'],
        'asyncio': ns['asyncio'],
        'requests': ns['requests'],
        'json': ns['json'],
        'TEXT': ns['TEXT'],
        'actions': ns['actions'],
        'input': ns['input'],
        'input_group': ns['input_group'],
        'run_js': ns['run_js'],
        'run_async': ns['run_async'],
        'run_asyncio_coroutine': ns['run_asyncio_coroutine'],
        'get_session_implement': ns['get_session_implement'],
        'set_env': ns['set_env'],
        'setup_admin_runtime': ns['setup_admin_runtime'],
        'basic_auth': ns['basic_auth'],
        'get_gpt_response': ns['get_gpt_response'],
        'put_out': ns['put_out'],
        'put_link': ns['put_link'],
        'put_text': ns['put_text'],
        'put_markdown': ns['put_markdown'],
        'put_table': ns['put_table'],
        'put_row': ns['put_row'],
        'put_html': ns['put_html'],
        'put_tabs': ns['put_tabs'],
        'put_button': ns['put_button'],
        'put_buttons': ns['put_buttons'],
        'put_collapse': ns['put_collapse'],
        'put_input': ns['put_input'],
        'put_logbox': ns['put_logbox'],
        'logbox_append': ns['logbox_append'],
        'set_scope': ns['set_scope'],
        'use_scope': ns['use_scope'],
        'clear': ns['clear'],
        'popup': ns['popup'],
        'toast': ns['toast'],
        'PASSWORD': ns['PASSWORD'],
        'datetime': ns['datetime'],
        'stable_widget_id': stable_widget_id,
        'edit_data_popup': ns.get('edit_data_popup'),
        'write_to_log': ns['write_to_log'],
        'sse_js': SSE_LOG_JS,
        'dynamic_popup': ns['dynamic_popup'],
        'truncate': ns['truncate'],
        'set_table_style': ns['set_table_style'],
        'apply_global_styles': ns['apply_global_styles'],
        'init_floating_menu_manager': init_floating_menu_manager,
        'create_nav_menu': create_nav_menu,
        'run_ai_in_worker': ns['run_ai_in_worker'],
        'render_llm_config_guide': ns['render_llm_config_guide'],  # 添加LLM配置引导函数
    }


def browser_ui_ctx(ns, admin_tables):
    return {
        'init_admin_ui': ns['init_admin_ui'],
        'NB': ns['NB'],
        'browser': ns['browser'],
        'tabs': ns['tabs'],
        'tab': ns['tab'],
        'first': ns['first'],
        'Stream': ns['Stream'],
        'timer': ns['timer'],
        'NS': ns['NS'],
        'log': ns['log'],
        'ls': ns['ls'],
        'print': ns['print'],
        'Dtalk': ns['Dtalk'],
        'pin': ns['pin'],
        'asyncio': ns['asyncio'],
        'requests': ns['requests'],
        'json': ns['json'],
        'TEXT': ns['TEXT'],
        'actions': ns['actions'],
        'input': ns['input'],
        'input_group': ns['input_group'],
        'run_js': ns['run_js'],
        'run_async': ns['run_async'],
        'run_asyncio_coroutine': ns['run_asyncio_coroutine'],
        'get_session_implement': ns['get_session_implement'],
        'set_env': ns['set_env'],
        'setup_admin_runtime': ns['setup_admin_runtime'],
        'basic_auth': ns['basic_auth'],
        'get_gpt_response': ns['get_gpt_response'],
        'put_out': ns['put_out'],
        'put_link': ns['put_link'],
        'put_text': ns['put_text'],
        'put_markdown': ns['put_markdown'],
        'put_table': ns['put_table'],
        'put_row': ns['put_row'],
        'put_html': ns['put_html'],
        'put_tabs': ns['put_tabs'],
        'put_button': ns['put_button'],
        'put_buttons': ns['put_buttons'],
        'put_collapse': ns['put_collapse'],
        'put_input': ns['put_input'],
        'put_logbox': ns['put_logbox'],
        'logbox_append': ns['logbox_append'],
        'set_scope': ns['set_scope'],
        'use_scope': ns['use_scope'],
        'clear': ns['clear'],
        'popup': ns['popup'],
        'toast': ns['toast'],
        'PASSWORD': ns['PASSWORD'],
        'datetime': ns['datetime'],
        'stable_widget_id': stable_widget_id,
        'edit_data_popup': ns.get('edit_data_popup'),
        'write_to_log': ns['write_to_log'],
        'sse_js': SSE_LOG_JS,
        'view_tab': ns['view_tab'],
        'close_tab': ns['close_tab'],
        'open_new_tab': ns['open_new_tab'],
        'show_browser_status': ns['show_browser_status'],
        'dynamic_popup': ns['dynamic_popup'],
        'summarize_tabs': ns['summarize_tabs'],
        'async_json_gpt': ns['async_json_gpt'],
        'extract_important_links': ns['extract_important_links'],
        'truncate': ns['truncate'],
        'set_table_style': ns['set_table_style'],
        'apply_global_styles': ns['apply_global_styles'],
        'process_tabs': ns['process_tabs'],
        'extended_reading': ns['extended_reading'],
        'close_all_tabs': ns['close_all_tabs'],
        'init_floating_menu_manager': init_floating_menu_manager,
        'create_nav_menu': create_nav_menu,
        'run_ai_in_worker': ns['run_ai_in_worker'],
    }


def config_ui_ctx(ns):
    return {
        'NB': ns['NB'],
        'init_admin_ui': ns['init_admin_ui'],
        'set_table_style': ns['set_table_style'],
        'apply_global_styles': ns['apply_global_styles'],
        'put_markdown': ns['put_markdown'],
        'put_text': ns['put_text'],
        'put_input': ns['put_input'],
        'put_button': ns['put_button'],
        'put_tabs': ns['put_tabs'],
        'use_scope': ns['use_scope'],
        'run_js': ns['run_js'],
        'run_async': ns['run_async'],
        'toast': ns['toast'],
        'popup': ns['popup'],
        'put_buttons': ns['put_buttons'],
        'pin': ns['pin'],
        'PASSWORD': ns['PASSWORD'],
    }
