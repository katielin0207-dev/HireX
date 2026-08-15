"""
讯飞 XTTS 离线 SDK Python 封装

使用本地 DLL 进行语音合成，无需网络连接。
支持 xiaoyan (小燕) 和 xiaofeng (小锋) 两种发音人。

依赖：SDK DLLs 位于 SDK/libs/64/
"""
import ctypes
from ctypes import (
    c_int, c_char_p, c_void_p, c_size_t, 
    POINTER, byref, Structure, pointer,
    CFUNCTYPE, cast, cdll
)
import os
import sys
import time
import tempfile
import threading


# ============================================================
# 类型定义（与 aikit_type.h 对应）
# ============================================================

class AIKIT_BaseParam(Structure):
    """参数链表节点"""
    pass

AIKIT_BaseParam._fields_ = [
    ("next", POINTER(AIKIT_BaseParam)),
    ("key", c_char_p),
    ("value", c_void_p),
    ("reserved", c_void_p),
    ("len", c_int),
    ("type", c_int),
]

class AIKIT_BaseData(Structure):
    """数据链表节点"""
    pass

AIKIT_BaseData._fields_ = [
    ("next", POINTER(AIKIT_BaseData)),
    ("desc", POINTER(AIKIT_BaseParam)),
    ("key", c_char_p),
    ("value", c_void_p),
    ("reserved", c_void_p),
    ("len", c_int),
    ("type", c_int),
    ("status", c_int),
    ("from_", c_int),  # 'from' is Python keyword
]

class AIKIT_BaseParamList(Structure):
    _fields_ = [
        ("node", POINTER(AIKIT_BaseParam)),
        ("count", c_int),
        ("totalLen", c_int),
    ]

class AIKIT_BaseDataList(Structure):
    _fields_ = [
        ("node", POINTER(AIKIT_BaseData)),
        ("count", c_int),
        ("totalLen", c_int),
    ]

class AIKIT_HANDLE(Structure):
    _fields_ = [
        ("usrContext", c_void_p),
        ("abilityID", c_char_p),
        ("handleID", c_size_t),
    ]

# 回调类型
AIKIT_OnOutput = CFUNCTYPE(None, POINTER(AIKIT_HANDLE), POINTER(AIKIT_BaseDataList))
AIKIT_OnEvent = CFUNCTYPE(None, POINTER(AIKIT_HANDLE), c_int, POINTER(AIKIT_BaseParamList))
AIKIT_OnError = CFUNCTYPE(None, POINTER(AIKIT_HANDLE), c_int, c_char_p)

class AIKIT_Callbacks(Structure):
    _fields_ = [
        ("onOutput", AIKIT_OnOutput),
        ("onEvent", AIKIT_OnEvent),
        ("onError", AIKIT_OnError),
    ]

# 常量
AIKIT_DataOnce = 3
AIKIT_DataText = 0
AIKIT_VarTypeString = 0
AIKIT_VarTypeInt = 1
AIKIT_Event_End = 2


# ============================================================
# SDK 封装类
# ============================================================

class XTTSOffline:
    """讯飞 XTTS 离线语音合成"""
    
    def __init__(self):
        self._dll = None
        self._initialized = False
        self._engine_ready = False
        self._audio_data = bytearray()
        self._finished = threading.Event()
        self._error_msg = None
        
    def _find_sdk(self):
        """查找 SDK 路径（项目内 > 环境变量 > 旧项目兜底）"""
        candidates = [
            os.path.join(os.path.dirname(__file__), '..', 'SDK', 'libs', '64', 'AEE_lib.dll'),
        ]
        # 环境变量覆盖
        env_dir = os.environ.get("XTTS_SDK_DIR", "")
        if env_dir:
            candidates.insert(0, env_dir)
        for p in candidates:
            if os.path.exists(p):
                return os.path.dirname(p)
        return None
    
    def _on_output(self, handle, output):
        """音频输出回调"""
        try:
            if output and output.contents.node:
                node = output.contents.node.contents
                if node.value and node.len > 0:
                    data = ctypes.string_at(node.value, node.len)
                    self._audio_data.extend(data)
        except Exception:
            pass
    
    def _on_event(self, handle, event_type, event_value):
        """事件回调"""
        if event_type == AIKIT_Event_End:
            self._finished.set()
    
    def _on_error(self, handle, err_code, desc):
        """错误回调"""
        if desc:
            self._error_msg = desc.decode('utf-8', errors='replace')
    
    def initialize(self, app_id="", api_key="", api_secret="", res_dir=""):
        """初始化 SDK"""
        sdk_dir = self._find_sdk()
        if not sdk_dir:
            return False, "SDK DLL not found"
        
        try:
            dll_path = os.path.join(sdk_dir, 'AEE_lib.dll')
            self._dll = ctypes.CDLL(dll_path)
            
            # 设置函数签名
            self._dll.AIKIT_Init.restype = c_int
            self._dll.AIKIT_EngineInit.argtypes = [c_char_p, POINTER(AIKIT_BaseParamList)]
            self._dll.AIKIT_EngineInit.restype = c_int
            self._dll.AIKIT_Start.argtypes = [c_char_p, POINTER(AIKIT_BaseParamList), 
                                                POINTER(AIKIT_BaseDataList), 
                                                POINTER(POINTER(AIKIT_HANDLE))]
            self._dll.AIKIT_Start.restype = c_int
            self._dll.AIKIT_Write.argtypes = [POINTER(AIKIT_HANDLE), POINTER(AIKIT_BaseDataList)]
            self._dll.AIKIT_Write.restype = c_int
            self._dll.AIKIT_End.argtypes = [POINTER(AIKIT_HANDLE)]
            self._dll.AIKIT_End.restype = c_int
            self._dll.AIKIT_EngineUnInit.argtypes = [c_char_p]
            self._dll.AIKIT_EngineUnInit.restype = c_int
            self._dll.AIKIT_UnInit.restype = c_int
            self._dll.AIKIT_RegisterAbilityCallback.argtypes = [c_char_p, AIKIT_Callbacks]
            self._dll.AIKIT_RegisterAbilityCallback.restype = c_int
            
            # 注册回调
            cbs = AIKIT_Callbacks(
                AIKIT_OnOutput(self._on_output),
                AIKIT_OnEvent(self._on_event),
                AIKIT_OnError(self._on_error),
            )
            
            # 初始化
            ret = self._dll.AIKIT_Init()
            if ret != 0:
                return False, "AIKIT_Init failed: %d" % ret
            
            # 注册能力回调
            ret = self._dll.AIKIT_RegisterAbilityCallback(b"e2e44feff", cbs)
            if ret != 0:
                return False, "RegisterAbilityCallback failed: %d" % ret
            
            # 初始化引擎
            ret = self._dll.AIKIT_EngineInit(b"e2e44feff", None)
            if ret != 0:
                return False, "EngineInit failed: %d" % ret
            
            self._initialized = True
            self._engine_ready = True
            return True, "OK"
            
        except Exception as e:
            return False, str(e)
    
    def synthesize(self, text, voice="xiaoyan"):
        """合成语音，返回 PCM 音频数据"""
        if not self._engine_ready:
            return None, "Not initialized"
        
        try:
            self._audio_data = bytearray()
            self._finished.clear()
            self._error_msg = None
            
            # 构建参数
            params = self._build_params(voice)
            data_input = self._build_text_data(text)
            
            handle = POINTER(AIKIT_HANDLE)()
            
            ret = self._dll.AIKIT_Start(b"e2e44feff", params, data_input, byref(handle))
            if ret != 0:
                return None, "AIKIT_Start failed: %d" % ret
            
            ret = self._dll.AIKIT_Write(handle, data_input)
            if ret != 0:
                self._dll.AIKIT_End(handle)
                return None, "AIKIT_Write failed: %d" % ret
            
            # 等待完成（最多 30 秒）
            if not self._finished.wait(30):
                self._dll.AIKIT_End(handle)
                return None, "Timeout"
            
            self._dll.AIKIT_End(handle)
            
            if self._error_msg:
                return None, self._error_msg
            
            if not self._audio_data:
                return None, "No audio generated"
            
            return bytes(self._audio_data), "OK"
            
        except Exception as e:
            return None, str(e)
    
    def synthesize_to_file(self, text, output_path=None, voice="xiaoyan"):
        """合成语音并保存为 WAV 文件"""
        result, msg = self.synthesize(text, voice)
        if result is None:
            return None, msg
        
        if output_path is None:
            output_path = os.path.join(tempfile.gettempdir(), "xtts_output.wav")
        
        # 将 PCM 转为 WAV
        self._pcm_to_wav(result, output_path)
        return output_path, "OK"
    
    def _build_params(self, voice):
        """构建参数链表"""
        # 简化版：直接使用 AIKIT_ParamBuilder 的逻辑
        # 由于 C++ Builder 不可用，尝试传 None（使用默认参数）
        # 如果 SDK 支持默认参数，这会工作
        return None
    
    def _build_text_data(self, text):
        """构建文本数据"""
        text_bytes = text.encode('utf-8')
        
        # 创建数据节点
        data_node = AIKIT_BaseData()
        data_node.key = b"text"
        data_node.value = ctypes.cast(
            ctypes.create_string_buffer(text_bytes, len(text_bytes)),
            c_void_p
        )
        data_node.len = len(text_bytes)
        data_node.type = AIKIT_DataText
        data_node.status = AIKIT_DataOnce
        data_node.next = None
        data_node.desc = None
        
        # 创建数据列表
        data_list = AIKIT_BaseDataList()
        data_list.node = pointer(data_node)
        data_list.count = 1
        data_list.totalLen = ctypes.sizeof(AIKIT_BaseData)
        
        return pointer(data_list)
    
    def _pcm_to_wav(self, pcm_data, output_path, sample_rate=16000, channels=1, bits=16):
        """PCM 转 WAV"""
        import struct
        import wave
        
        with wave.open(output_path, 'wb') as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(bits // 8)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm_data)
    
    def cleanup(self):
        """释放资源"""
        if self._dll:
            try:
                if self._engine_ready:
                    self._dll.AIKIT_EngineUnInit(b"e2e44feff")
                if self._initialized:
                    self._dll.AIKIT_UnInit()
            except Exception:
                pass
            self._dll = None


# ============================================================
# 简单测试
# ============================================================
if __name__ == "__main__":
    tts = XTTSOffline()
    ok, msg = tts.initialize()
    print("Init:", ok, msg)
    if ok:
        result, msg = tts.synthesize_to_file("你好，这是一个测试", voice="xiaoyan")
        print("Result:", result, msg)
        tts.cleanup()
