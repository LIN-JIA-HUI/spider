### **資料欄位對照表**

| **分類**               | **屬性英文**      | **屬性名稱**    | **預設值** |
|------------------------|-------------------|-----------------|-----------|
| **Board Design (顯卡基本規格)**        | Length            | 長度            | null      |
|                        | Width             | 寬度            | null      |
|                        | Height            | 高度            | null      |
|                        | DisplayOutputs    | 輸出接口        | null      |
|                        | SlotWidth         | 插槽寬度        | null      |
|                        | TDP               | TDP             | null      |
|                        | SuggestedPSU      | 建議電源        | null      |
|                        | PowerConnectors       | 電源接口        | null      |
|                        | BoardNumber       | 板卡型號        | null      |
| **Graphics Card (板卡設計)**       | ReleaseDate       | 發布日期        | null      |
|                        | Announced         | 公告日期        | null      |
| **Clock Speeds (時脈速度)**        | BaseClock         | 基礎時脈        | null      |
|                        | BoostClock        | 加速時脈        | null      |
|                        | MemoryClock       | 記憶體時脈      | null      |
| **Physical Properties (物理特性與散熱)** | Weight            | 重量            | null      |
|                        | Pipe       | 熱管數量        | null      |
|                        | IdleGPUTemp (新增)             | 閒置溫度            | null      |
|                        | GamingGPUTemp (原Temp)            | 負載溫度            | null      |
|                        | MemoryTemp (新增)             | 記憶體溫度            | null      |
|                        | Noice             | 噪音            | null      |
| **TDP Compare (功耗超頻)**         | TDPComparison     | 預設功耗        | null      |
|                        | TDPDefault        | 最大功耗        | null      |
|                        | TDPMax            | 功耗比較        | null      |
|                        | AvgGPUClock   | Avg. GPU Clock  | null      |
|                        | MaxMemoryClock       | Max. Memory Clock | null      |
|                        | Performance    | Performance     | null      |
|                        | PwrLimitDefMax       | Pwr Limit Def/Max | null      |
|                        | OCPerfMaxPwr    | OC Perf at Max Pwr | null      |
| **GPU**                 | GPUMEMCount       | MEM顆數         | null      |
|                        | GPUControllerModel| 控制器型號      | null      |
|                        | GPUMOSSpec        | MOS規格         | null      |
| **Memory**              | MemoryMEMCount    | MEM顆數         | null      |
|                        | MemoryControllerModel| 控制器型號    | null      |
|                        | MemoryMOSSpec     | MOS規格         | null      |

### 爬蟲API
- 尚未爬取的顯卡系列: http://localhost:8000/run-scraper
- 更新所有review資料: http://localhost:8000/run-scraper?mode=full
