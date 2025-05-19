# **COMP5349 Assignment 2 \- 项目设计文档**

## **一、通用约定和细节 (General Conventions & Details)**

### **1\. 唯一ID命名规范**

所有模块、函数等应遵循以下命名规范，以便清晰识别和管理：  
PROJECT\_PREFIX-COMPONENT\_TYPE-COMPONENT\_NAME-FUNCTION\_NAME (如果适用)。

* PROJECT\_PREFIX: COMP5349\_A2  
* COMPONENT\_TYPE:  
  * WEB: Web应用相关组件 (例如 Flask 应用本身，其下的主要模块)  
  * UTIL: 工具类模块 (例如 s3\_utils, db\_utils)  
  * LAMBDA: Lambda函数  
  * DB\_SCRIPT: 数据库脚本 (例如 Schema 定义)  
  * DEPLOYMENT: 部署架构相关  
* COMPONENT\_NAME: 组件的具体名称 (例如, S3, DB, APPMAIN, ANNOTATION, THUMBNAIL, SCHEMA, ARCHITECTURE)  
* FUNCTION\_NAME: 函数名 (小写下划线)

**示例：**

* COMP5349\_A2-UTIL-S3-upload\_file\_to\_s3  
* COMP5349\_A2-LAMBDA-ANNOTATION-lambda\_handler  
* COMP5349\_A2-WEB-APPMAIN-upload\_post  
* COMP5349\_A2-DB\_SCRIPT-SCHEMA

### **2\. 全局错误处理策略**

#### **2.1 自定义异常**

项目将定义一套共用的自定义异常体系，以提供更具体的错误信息。

* **基类：** COMP5349A2Error(Exception)  
  * 属性：  
    * message (str): 人类可读的错误信息。  
    * error\_code (str, optional): 应用程序定义的唯一错误码 (大写下划线)。  
    * original\_exception (Exception, optional): 原始的Python异常对象，用于调试。  
* **具体异常类 (继承自 COMP5349A2Error)：**  
  * S3InteractionError: S3操作（上传、下载、生成预签名URL等）相关错误。  
  * DatabaseError: 数据库操作（连接、查询、更新等）相关错误。  
  * GeminiAPIError: 调用Google Gemini API相关错误。  
  * ImageProcessingError: 图片处理（如缩略图生成）相关错误。  
  * InvalidInputError: 用户输入或函数参数校验错误。  
  * ConfigurationError: 项目配置（如环境变量缺失）问题错误。

#### **2.2 错误响应格式**

* API/Lambda HTTP响应 (若通过API Gateway暴露):  
  如果Flask应用或API Gateway需要返回JSON格式的错误响应，应遵循以下结构：  
  {  
    "error": {  
      "type": "S3InteractionError", // 异常类名  
      "code": "S3\_UPLOAD\_FAILED",  // 具体的错误码 (大写下划线)  
      "message": "Failed to upload file to S3.", // 人类可读信息  
      "details": "Optional: further details or original error message snippet if safe to expose.", // 可选的详细信息  
      "request\_id": "unique\_request\_id\_if\_available" // 关联的请求ID  
    }  
  }

* S3直接触发的Lambda:  
  主要通过CloudWatch Logs记录详细错误。如果配置了死信队列 (DLQ)，处理失败的事件将进入DLQ。

### **3\. 日志记录标准**

* **日志格式：** 统一采用 **JSON格式日志**，方便CloudWatch Logs Insights进行分析和查询。  
* **必含字段：**  
  * timestamp: ISO 8601格式的时间戳 (e.g., 2023-10-27T10:30:00.123Z)。  
  * level: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)。  
  * module: 产生日志的模块名 (e.g., s3\_utils, app.py, annotation\_lambda)。  
  * function: 产生日志的函数名 (e.g., upload\_file\_to\_s3, upload\_post, lambda\_handler)。  
  * message: 具体的日志信息 (str)。  
  * request\_id: 请求追踪ID (如果可用，见下文)。  
  * aws\_request\_id: (仅Lambda) Lambda执行上下文提供的请求ID。  
* **可选字段 (根据上下文添加)：**  
  * s3\_bucket, s3\_key: S3操作相关。  
  * db\_table: 数据库操作相关。  
  * error\_code: 自定义异常的错误码。  
  * exception\_type: 捕获到的异常类型名。  
  * exception\_message: 捕获到的异常信息。  
  * stack\_trace: (仅ERROR/CRITICAL级别) 异常的堆栈跟踪。  
  * 其他与业务逻辑相关的上下文信息。  
* **关键信息点记录：**  
  * **S3操作：** 必须记录 bucket, key, 操作类型 (upload, download, generate\_presigned\_url), 成功/失败状态。  
  * **DB操作：** 必须记录表名，操作类型 (insert, select, update), 简化的查询条件 (避免敏感数据泄露，例如只记录 WHERE id \= ? 而不是具体id值，除非是内部生成的key如original\_s3\_key)，成功/失败状态，影响行数 (如果适用)。  
  * **API调用 (Gemini)：** 必须记录调用的API端点/模型名，请求的摘要 (e.g., "captioning image s3://bucket/key")，响应状态码/状态，成功/失败状态。  
* **请求ID追踪 (Correlation ID)：**  
  * **强烈推荐启用。**  
  * **Flask应用 (app.py):** 在收到请求时 (例如在 @app.before\_request 中) 生成一个唯一的 request\_id (e.g., str(uuid.uuid4().hex))，并将其存储在 flask.g 对象中，以便在整个请求处理周期内访问。所有日志记录都应包含此 request\_id。  
  * **Lambda函数:** Lambda上下文对象 (context) 提供了 aws\_request\_id，应在所有日志记录中使用。  
  * **传递 request\_id 到S3触发的Lambda (可选增强):**  
    * **方案：** 在Flask应用上传文件到S3时，将Web应用生成的 request\_id 作为S3对象的元数据 (e.g., x-amz-meta-request-id) 进行设置。S3事件触发的Lambda函数在处理事件时，可以读取该S3对象的元数据来获取此 request\_id，从而将Web请求与Lambda执行关联起来。  
    * **当前决策：** 此方案作为加分项考虑。基础实现中，S3触发的Lambda将使用其自身的 aws\_request\_id 进行追踪。

### **4\. 环境变量命名约定**

所有环境变量名使用大写字母和下划线。

* **DB相关：**  
  * DB\_HOST: 数据库主机名。  
  * DB\_USER: 数据库用户名。  
  * DB\_PASSWORD: 数据库密码 (推荐通过Secrets Manager管理)。  
  * DB\_NAME: 数据库名称。  
  * DB\_PORT: 数据库端口 (如果非默认3306)。  
* **S3相关：**  
  * S3\_IMAGE\_BUCKET: 存放原始图片和缩略图的主S3桶名。  
* **Gemini API相关：**  
  * GEMINI\_API\_KEY: Google Gemini API密钥 (推荐通过Secrets Manager管理)。  
  * GEMINI\_MODEL\_NAME: 使用的Gemini模型名称 (e.g., gemini-pro-vision)。  
  * GEMINI\_PROMPT: 调用Gemini API时使用的默认提示文本。  
* **Flask应用相关：**  
  * FLASK\_SECRET\_KEY: Flask应用用于会话管理和flash消息的密钥。  
* **Lambda特定配置：**  
  * THUMBNAIL\_SIZE: 缩略图目标尺寸 (e.g., "128x128")。  
* **通用配置：**  
  * LOG\_LEVEL: 应用的日志级别 (e.g., INFO, DEBUG)。

### **5\. Python版本和依赖管理**

* **统一Python版本：** **Python 3.9**。这是AWS Lambda支持较好且稳定的版本。  
* **依赖管理 (requirements.txt)：**  
  * 所有Python依赖项及其版本应在各自模块的 requirements.txt 文件中明确指定。  
  * 版本号使用精确指定 \== (例如 boto3==1.28.0, Pillow==9.5.0)，以保证开发、测试和生产环境的一致性，避免因小版本更新引入的意外问题。

## **二、Web 应用 (web\_app/)**

### **1\. utils/s3\_utils.py**

Module ID: COMP5349\_A2-UTIL-S3  
Purpose: 提供与AWS S3服务交互的工具函数，包括文件上传和生成预签名URL。

#### **upload\_file\_to\_s3(file\_stream, bucket\_name: str, s3\_key: str, content\_type: str, request\_id: Optional\[str\] \= None) \-\> bool**

* **Unique ID:** COMP5349\_A2-UTIL-S3-upload\_file\_to\_s3  
* **职责 (Responsibility):** 将给定的文件流上传到指定的S3桶和键，并设置正确的ContentType。  
* **输入规范 (Detailed Input Specification):**  
  * file\_stream: io.BytesIO 对象或 werkzeug FileStorage 对象 (Flask上传的文件对象)。函数应能处理这两种类型。  
  * bucket\_name (str): 目标S3桶的名称。从环境变量 S3\_IMAGE\_BUCKET 获取。  
  * s3\_key (str): 在S3桶中存储对象的键。此函数不负责生成s3\_key，它必须由调用者（app.py）在调用此函数前完全确定并传入。命名规则应遵循S3安全字符集，长度不超过1024字节。  
  * content\_type (str): 图片的MIME类型 (e.g., 'image/jpeg', 'image/png')。此参数必须提供。  
  * request\_id (Optional\[str\]): 用于日志追踪的请求ID。  
* **输出规范 (Detailed Output Specification):**  
  * 成功时返回 True。  
  * 失败时，抛出 S3InteractionError 异常，其中应包含具体的错误信息、S3错误码和可能的原始Boto3异常。  
* **核心业务逻辑步骤 (Core Business Logic Steps):**  
  1. 初始化 boto3.client('s3')。  
  2. 调用 s3\_client.upload\_fileobj() 方法。  
  3. 在 ExtraArgs 参数中设置 {'ContentType': content\_type}。  
  4. (可选增强) 如果提供了 request\_id 并且启用了通过S3元数据传递追踪ID的方案，则在 ExtraArgs 中增加 Metadata={'request\_id': request\_id}。当前版本可不实现此可选增强。  
* **副作用说明 (Side Effects):**  
  * 文件被上传到S3。  
  * S3对象的 ContentType 元数据被设置。  
* **错误处理 (Error Handling):**  
  * 捕获 botocore.exceptions.NoCredentialsError, botocore.exceptions.ClientError 等Boto3可能抛出的异常。  
  * 从 ClientError.response\['Error'\]\['Code'\] 获取S3返回的具体错误码 (e.g., NoSuchBucket, AccessDenied)。  
  * 所有捕获的异常都应包装成 S3InteractionError(message=..., error\_code=s3\_error\_code, original\_exception=e) 抛出。  
* **日志记录要求 (Logging Requirements):**  
  * **成功：** INFO 级别，记录 "Successfully uploaded {s3\_key} to bucket {bucket\_name} with ContentType {content\_type}."，包含 request\_id。  
  * **失败：** ERROR 级别，记录 "Failed to upload {s3\_key} to bucket {bucket\_name}. Error: {error\_message}"，并包含 s3\_error\_code 和 request\_id。  
* **验收标准/关键测试用例 (Acceptance Criteria / Key Test Cases):**  
  * test\_upload\_with\_specific\_content\_type: 传入 image/jpeg，验证 ExtraArgs 中 ContentType 被正确设置。  
  * test\_upload\_werkzeug\_filestorage\_object: 验证函数能正确处理Flask的 FileStorage 对象。  
  * test\_upload\_bytesio\_object: 验证函数能正确处理 io.BytesIO 对象。  
  * test\_upload\_raises\_S3InteractionError\_on\_NoCredentialsError: 模拟 NoCredentialsError。  
  * test\_upload\_raises\_S3InteractionError\_on\_NoSuchBucket: 模拟 ClientError 中的 NoSuchBucket。  
  * test\_upload\_raises\_S3InteractionError\_on\_AccessDenied: 模拟 ClientError 中的 AccessDenied。

#### **generate\_presigned\_url(bucket\_name: str, s3\_key: str, expiration\_seconds: int \= 3600, request\_id: Optional\[str\] \= None) \-\> Optional\[str\]**

* **Unique ID:** COMP5349\_A2-UTIL-S3-generate\_presigned\_url  
* **职责 (Responsibility):** 为S3桶中的指定对象生成一个有时效性的预签名GET URL。  
* **输入规范 (Detailed Input Specification):**  
  * bucket\_name (str): S3桶的名称。  
  * s3\_key (str): S3对象的键。  
  * expiration\_seconds (int): URL的有效时间（秒）。默认3600秒 (1小时)。函数应校验此值在合理范围内 (e.g., 最小值60秒，最大值604800秒即7天)。如果超出范围，抛出 InvalidInputError。  
  * request\_id (Optional\[str\]): 用于日志追踪的请求ID。  
* **输出规范 (Detailed Output Specification):**  
  * 成功时返回生成的预签名URL字符串。  
  * 失败时，抛出 S3InteractionError。  
* **核心业务逻辑步骤 (Core Business Logic Steps):**  
  1. 校验 expiration\_seconds 是否在允许范围内。  
  2. 初始化 boto3.client('s3')。  
  3. 调用 s3\_client.generate\_presigned\_url() 方法，参数包括：  
     * ClientMethod='get\_object'  
     * Params={'Bucket': bucket\_name, 'Key': s3\_key}  
     * ExpiresIn=expiration\_seconds  
* **错误处理 (Error Handling):**  
  * 捕获 botocore.exceptions.ClientError (例如，如果S3服务本身有问题，或key包含无效字符) 或 NoCredentialsError。  
  * 所有捕获的异常都应包装成 S3InteractionError 抛出。  
  * 如果 expiration\_seconds 无效，抛出 InvalidInputError。  
* **日志记录要求 (Logging Requirements):**  
  * **成功：** INFO 级别，记录 "Successfully generated presigned URL for s3://{bucket\_name}/{s3\_key} expiring in {expiration\_seconds}s."，包含 request\_id。  
  * **失败 (包括输入校验失败)：** ERROR 级别，记录 "Failed to generate presigned URL for s3://{bucket\_name}/{s3\_key}. Error: {error\_message}"，包含 request\_id。  
* **验收标准/关键测试用例 (Acceptance Criteria / Key Test Cases):**  
  * test\_generate\_url\_success\_returns\_string  
  * test\_generate\_url\_invalid\_expiration\_raises\_InvalidInputError  
  * test\_generate\_url\_s3\_client\_error\_raises\_S3InteractionError

### **2\. utils/db\_utils.py**

Module ID: COMP5349\_A2-UTIL-DB  
Purpose: 提供与RDS MySQL数据库交互的工具函数，包括连接管理和数据操作。

#### **get\_db\_connection()**

* **Unique ID:** COMP5349\_A2-UTIL-DB-get\_db\_connection  
* **职责 (Responsibility):** 创建并返回一个新的MySQL数据库连接。  
* **输入规范 (Detailed Input Specification):** 无。  
* **输出规范 (Detailed Output Specification):**  
  * 成功时返回一个 mysql.connector.connection.MySQLConnection 对象。  
  * 失败时抛出 ConfigurationError (如果环境变量缺失) 或 DatabaseError (如果连接失败)。  
* **核心业务逻辑步骤 (Core Business Logic Steps):**  
  1. 从环境变量读取数据库连接参数：DB\_HOST, DB\_USER, DB\_PASSWORD, DB\_NAME, DB\_PORT (如果 DB\_PORT 未设置，则使用MySQL默认端口3306)。  
  2. 检查必要的环境变量是否存在，如果缺失，记录错误并抛出 ConfigurationError。  
  3. 使用 mysql.connector.connect() 尝试建立连接。可以考虑设置合理的 connect\_timeout (e.g., 10秒)，暂用默认。  
* **错误处理 (Error Handling):**  
  * 捕获 mysql.connector.Error，包装为 DatabaseError(message="Failed to connect to database.", original\_exception=e) 抛出。  
  * 如果环境变量缺失，抛出 ConfigurationError。  
* **日志记录要求 (Logging Requirements):**  
  * **成功：** DEBUG 级别，记录 "Database connection established successfully to {DB\_HOST}/{DB\_NAME}."  
  * **失败 (环境变量缺失)：** ERROR 级别，记录 "Database configuration environment variable(s) missing."  
  * **失败 (连接错误)：** ERROR 级别，记录 "Failed to connect to database {DB\_HOST}/{DB\_NAME}. Error: {error\_message}"。

#### **save\_initial\_image\_meta(db\_conn, original\_s3\_key: str, request\_id: Optional\[str\] \= None) \-\> int**

* **Unique ID:** COMP5349\_A2-UTIL-DB-save\_initial\_image\_meta  
* **职责 (Responsibility):** 在images表中插入一条新的图片元数据记录，状态默认为'pending'。  
* **输入规范 (Detailed Input Specification):**  
  * db\_conn: 已建立的数据库连接对象。  
  * original\_s3\_key (str): 图片在S3上的唯一键。此键在images表中应具有UNIQUE约束。  
  * request\_id (Optional\[str\]): 用于日志追踪的请求ID。  
* **输出规范 (Detailed Output Specification):**  
  * 成功时返回新插入记录的 id (通过 cursor.lastrowid)。  
  * 失败时抛出 DatabaseError。如果是因为唯一约束冲突，error\_code 可以是 DB\_UNIQUE\_VIOLATION。  
* **核心业务逻辑步骤 (Core Business Logic Steps):**  
  1. 获取数据库游标 cursor \= db\_conn.cursor()。  
  2. 准备SQL INSERT语句：  
     INSERT INTO images   
     (original\_s3\_key, uploaded\_at, caption\_status, thumbnail\_status)   
     VALUES (%s, CURRENT\_TIMESTAMP, 'pending', 'pending')

  3. 使用参数化查询执行SQL: cursor.execute(sql, (original\_s3\_key,))。  
  4. 提交事务: db\_conn.commit()。  
  5. 获取新插入记录的ID: new\_id \= cursor.lastrowid。  
  6. 关闭游标: cursor.close()。  
* **错误处理 (Error Handling):**  
  * 捕获 mysql.connector.Error 作为基类。  
  * 如果 err.errno \== errorcode.ER\_DUP\_ENTRY (对于 mysql-connector-python)，则包装为 DatabaseError(message=f"Duplicate entry for original\_s3\_key: {original\_s3\_key}.", error\_code="DB\_UNIQUE\_VIOLATION", original\_exception=e) 抛出。  
  * 其他 mysql.connector.Error 包装为通用的 DatabaseError (例如，message=f"Failed to save initial metadata for {original\_s3\_key}. Error: {e}") 抛出。  
  * 在异常情况下，应确保事务回滚（尽管对于单条INSERT且自动提交关闭时，连接关闭会自动回滚未提交事务，但显式回滚更安全，或者依赖于上层如Flask的teardown处理）。  
* **日志记录要求 (Logging Requirements):**  
  * **成功：** INFO 级别，记录 "Successfully saved initial metadata for {original\_s3\_key}, new\_id={new\_id}."，包含 request\_id。  
  * **失败：** ERROR 级别，记录 "Failed to save initial metadata for {original\_s3\_key}. Error: {error\_message}"，包括 error\_code 和 request\_id。

#### **get\_all\_image\_data\_for\_gallery(db\_conn, request\_id: Optional\[str\] \= None) \-\> list\[dict\]**

* **Unique ID:** COMP5349\_A2-UTIL-DB-get\_all\_image\_data\_for\_gallery  
* **职责 (Responsibility):** 从images表中检索所有图片的元数据，用于画廊页面展示。  
* **输入规范 (Detailed Input Specification):**  
  * db\_conn: 已建立的数据库连接对象。  
  * request\_id (Optional\[str\]): 用于日志追踪的请求ID。  
* **输出规范 (Detailed Output Specification):**  
  * 返回一个字典列表。每个字典代表一条图片记录，key与images表的列名一致：id, original\_s3\_key, caption, thumbnail\_s3\_key, caption\_status, thumbnail\_status, uploaded\_at。  
  * uploaded\_at 应为Python datetime.datetime 对象。  
  * 列表按 uploaded\_at DESC (最新上传的在前) 排序。  
  * 如果查询失败，抛出 DatabaseError。  
* **核心业务逻辑步骤 (Core Business Logic Steps):**  
  1. 获取数据库游标 cursor \= db\_conn.cursor(dictionary=True) (使用 dictionary=True 使结果行为字典)。  
  2. 准备SQL SELECT语句：  
     SELECT id, original\_s3\_key, caption, thumbnail\_s3\_key, caption\_status, thumbnail\_status, uploaded\_at   
     FROM images   
     ORDER BY uploaded\_at DESC

  3. 执行SQL: cursor.execute(sql)。  
  4. 获取所有结果: results \= cursor.fetchall()。  
  5. 关闭游标: cursor.close()。  
  6. 返回 results。  
* **错误处理 (Error Handling):**  
  * 查询失败时，捕获 mysql.connector.Error，包装为 DatabaseError(message="Failed to retrieve images for gallery.", original\_exception=e) 抛出。  
* **日志记录要求 (Logging Requirements):**  
  * **成功查询到数据：** INFO 级别，记录 "Retrieved {len(results)} images for gallery."，包含 request\_id。  
  * **查询结果为空：** INFO 级别，记录 "No images found for gallery."，包含 request\_id。  
  * **失败：** ERROR 级别，记录 "Database query failed for gallery. Error: {error\_message}"，包含 request\_id。

#### **update\_caption\_in\_db(db\_conn, original\_s3\_key: str, caption\_text: Optional\[str\], status: str, request\_id: Optional\[str\] \= None) \-\> bool**

* **Unique ID:** COMP5349\_A2-UTIL-DB-update\_caption\_in\_db  
* **职责 (Responsibility):** 更新指定图片的标注文本和标注状态。  
* **输入规范 (Detailed Input Specification):**  
  * db\_conn: 已建立的数据库连接对象。  
  * original\_s3\_key (str): 要更新记录的图片S3键。  
  * caption\_text (Optional\[str\]): 生成的标注文本。如果 status 是 'failed'，此项可能为 None 或包含错误信息。  
  * status (str): 标注状态，必须是 'completed' 或 'failed'。函数内部应校验。如果无效，抛出 InvalidInputError。  
  * request\_id (Optional\[str\]): 用于日志追踪的请求ID (通常是Lambda的 aws\_request\_id)。  
* **输出规范 (Detailed Output Specification):**  
  * 成功更新且影响了至少一行记录时返回 True。  
  * 如果未找到对应 original\_s3\_key 的记录 (即 cursor.rowcount \== 0)，返回 False 并记录警告。  
  * 如果输入 status 无效，抛出 InvalidInputError。  
  * 如果数据库操作失败，抛出 DatabaseError。  
* **核心业务逻辑步骤 (Core Business Logic Steps):**  
  1. 校验 status 参数是否为 'completed' 或 'failed'。如果不是，抛出 InvalidInputError。  
  2. 获取数据库游标 cursor \= db\_conn.cursor()。  
  3. 准备SQL UPDATE语句：  
     UPDATE images   
     SET caption \= %s, caption\_status \= %s   
     WHERE original\_s3\_key \= %s

  4. 执行SQL: cursor.execute(sql, (caption\_text, status, original\_s3\_key))。  
  5. 提交事务: db\_conn.commit()。  
  6. 检查影响的行数: affected\_rows \= cursor.rowcount。  
  7. 关闭游标: cursor.close()。  
  8. 返回 affected\_rows \> 0。  
* **错误处理 (Error Handling):**  
  * 捕获 mysql.connector.Error，包装为 DatabaseError 抛出。  
* **日志记录要求 (Logging Requirements):**  
  * **成功更新：** INFO 级别，记录 "Updated caption for {original\_s3\_key} to status {status}. Affected rows: {affected\_rows}." (如果 caption\_text 过长，不建议全量记录，可记录其摘要或长度)，包含 request\_id。  
  * **记录未找到:** WARNING 级别，当 affected\_rows \== 0 时记录 "{original\_s3\_key} not found in DB for caption update."，包含 request\_id。  
  * **无效状态参数：** ERROR 级别，记录 "Invalid status parameter '{status}' for update\_caption\_in\_db."，包含 request\_id。  
  * **数据库操作失败：** ERROR 级别，记录 "Failed to update caption for {original\_s3\_key}. Error: {error\_message}."，包含 request\_id。  
* **验收标准/关键测试用例 (Acceptance Criteria / Key Test Cases):**  
  * test\_update\_caption\_success\_completed  
  * test\_update\_caption\_success\_failed\_with\_error\_message\_in\_caption  
  * test\_update\_caption\_invalid\_status\_param\_raises\_InvalidInputError  
  * test\_update\_caption\_s3\_key\_not\_found\_returns\_false\_and\_logs\_warning  
  * test\_update\_caption\_db\_error\_raises\_DatabaseError

#### **update\_thumbnail\_info\_in\_db(db\_conn, original\_s3\_key: str, thumbnail\_s3\_key: Optional\[str\], status: str, request\_id: Optional\[str\] \= None) \-\> bool**

* **Unique ID:** COMP5349\_A2-UTIL-DB-update\_thumbnail\_info\_in\_db  
* **职责 (Responsibility):** 更新指定图片的缩略图S3 key和缩略图生成状态。  
* **输入规范 (Detailed Input Specification):**  
  * db\_conn: 已建立的数据库连接对象。  
  * original\_s3\_key (str): 要更新记录的原始图片S3键。  
  * thumbnail\_s3\_key (Optional\[str\]): 生成的缩略图S3键。如果 status 是 'failed'，此项应为 None。  
  * status (str): 缩略图生成状态，必须是 'completed' 或 'failed'。函数内部应校验。如果无效，抛出 InvalidInputError。  
  * request\_id (Optional\[str\]): 用于日志追踪的请求ID (通常是Lambda的 aws\_request\_id)。  
* **输出规范 (Detailed Output Specification):**  
  * 成功更新且影响了至少一行记录时返回 True。  
  * 如果未找到对应 original\_s3\_key 的记录，返回 False 并记录警告。  
  * 如果输入 status 无效，抛出 InvalidInputError。  
  * 如果数据库操作失败，抛出 DatabaseError。  
* **核心业务逻辑步骤 (Core Business Logic Steps):**  
  1. 校验 status 参数。  
  2. 获取数据库游标 cursor \= db\_conn.cursor()。  
  3. 准备SQL UPDATE语句：  
     UPDATE images   
     SET thumbnail\_s3\_key \= %s, thumbnail\_status \= %s   
     WHERE original\_s3\_key \= %s

  4. 执行SQL: cursor.execute(sql, (thumbnail\_s3\_key, status, original\_s3\_key))。  
  5. 提交事务: db\_conn.commit()。  
  6. 检查影响的行数并返回。  
  7. 关闭游标。  
* **错误处理 (Error Handling):** 同 update\_caption\_in\_db。  
* **日志记录要求 (Logging Requirements):** 类似 update\_caption\_in\_db，将 "caption" 替换为 "thumbnail info"。  
* **验收标准/关键测试用例 (Acceptance Criteria / Key Test Cases):** 类似 update\_caption\_in\_db 的测试用例，适配缩略图场景。

### **3\. web\_app/app.py (Flask Application Routes and Logic)**

Module ID: COMP5349\_A2-WEB-APPMAIN  
Purpose: 定义Flask Web应用，包括路由、请求处理器和整体应用逻辑。它协调用户请求、S3工具和数据库工具之间的交互。

#### **全局应用配置与设置 (Global Application Configuration & Setup)**

* **Flask App 初始化:**  
  import os  
  import uuid  
  from flask import Flask, request, redirect, url\_for, render\_template, flash, g  
  from werkzeug.utils import secure\_filename  
  \# Assuming utils are in a 'utils' subdirectory or package  
  from .utils import s3\_utils, db\_utils   
  from .utils.custom\_exceptions import COMP5349A2Error, S3InteractionError, DatabaseError, InvalidInputError, ConfigurationError  
  \# TODO: Setup JSON logging

  app \= Flask(\_\_name\_\_)  
  app.config\['SECRET\_KEY'\] \= os.environ.get('FLASK\_SECRET\_KEY', 'a\_very\_secret\_dev\_key\_for\_development\_only')  
  app.config\['MAX\_CONTENT\_LENGTH'\] \= 16 \* 1024 \* 1024  \# 16 MB  
  app.config\['S3\_IMAGE\_BUCKET'\] \= os.environ.get('S3\_IMAGE\_BUCKET')  
  app.config\['ALLOWED\_EXTENSIONS'\] \= {'png', 'jpg', 'jpeg', 'gif'}  
  \# TODO: Configure logger instance (app.logger) to use JSON formatter and set LOG\_LEVEL from env

* **AWS 凭证:** 假定由EC2实例角色处理，Boto3将自动获取。  
* **数据库连接管理:** 使用 flask.g 对象管理请求范围内的数据库连接。  
  @app.before\_request  
  def before\_request\_tasks():  
      g.request\_id \= str(uuid.uuid4().hex) \# Generate request\_id for this request  
      try:  
          \# Attempt to get DB connection for each request  
          g.db\_conn \= db\_utils.get\_db\_connection()  
          \# app.logger.debug("Database connection established for request.", extra={'request\_id': g.request\_id})  
      except ConfigurationError as e:  
          app.logger.error(f"Configuration error preventing DB connection: {e.message}", extra={'request\_id': g.request\_id, 'error\_code': getattr(e, 'error\_code', None)})  
          g.db\_conn \= None \# Ensure it's None so routes can check  
          \# This error might be critical enough to abort, or let routes handle g.db\_conn being None  
      except DatabaseError as e:  
          app.logger.error(f"Database connection failed in before\_request: {e.message}", extra={'request\_id': g.request\_id, 'error\_code': getattr(e, 'error\_code', None)})  
          g.db\_conn \= None \# Ensure it's None

  @app.teardown\_appcontext  
  def teardown\_db(exception=None):  
      db\_conn \= g.pop('db\_conn', None)  
      request\_id \= getattr(g, 'request\_id', 'N/A') \# Retrieve request\_id  
      if db\_conn is not None:  
          try:  
              db\_conn.close()  
              \# app.logger.debug("Database connection closed.", extra={'request\_id': request\_id})  
          except Exception as e:  
              app.logger.error(f"Error closing DB connection: {str(e)}", extra={'request\_id': request\_id})

      if exception: \# Log any unhandled exceptions that occurred during the request  
          app.logger.error(f"Unhandled exception in request context: {exception}", exc\_info=True, extra={'request\_id': request\_id})

* 全局错误处理器 (Global Error Handlers):  
  需要一个 error.html 模板来显示错误信息。  
  @app.errorhandler(DatabaseError)  
  def handle\_database\_error(error):  
      request\_id \= getattr(g, 'request\_id', 'N/A')  
      app.logger.error(f"DatabaseError caught by errorhandler: {error.message}", exc\_info=True, extra={'request\_id': request\_id, 'error\_code': error.error\_code})  
      flash(f"A database error occurred: {error.message}. Please try again later.", 'danger')  
      return render\_template('error.html', error\_message="A critical database error occurred.", error\_code=500, request\_id=request\_id), 500

  @app.errorhandler(S3InteractionError)  
  def handle\_s3\_error(error):  
      request\_id \= getattr(g, 'request\_id', 'N/A')  
      app.logger.error(f"S3InteractionError caught by errorhandler: {error.message}", exc\_info=True, extra={'request\_id': request\_id, 'error\_code': error.error\_code})  
      flash(f"An S3 interaction error occurred: {error.message}. Please try again later.", 'danger')  
      return render\_template('error.html', error\_message="A critical S3 error occurred.", error\_code=500, request\_id=request\_id), 500

  @app.errorhandler(InvalidInputError)  
  def handle\_invalid\_input\_error(error):  
      request\_id \= getattr(g, 'request\_id', 'N/A')  
      app.logger.warning(f"InvalidInputError caught: {error.message}", exc\_info=True, extra={'request\_id': request\_id, 'error\_code': error.error\_code})  
      flash(f"Invalid input: {error.message}", 'warning')  
      \# Redirect back to the referrer or a safe page like index.  
      \# Avoid rendering a template that might depend on the invalid input.  
      return redirect(request.referrer or url\_for('index\_get'))

  @app.errorhandler(404)  
  def page\_not\_found(error):  
      request\_id \= getattr(g, 'request\_id', 'N/A')  
      app.logger.info(f"404 Not Found: {request.path}", extra={'request\_id': request\_id})  
      return render\_template('error.html', error\_message="Page Not Found. The requested URL was not found on the server.", error\_code=404, request\_id=request\_id), 404

  @app.errorhandler(413)  
  def payload\_too\_large(error):  
      request\_id \= getattr(g, 'request\_id', 'N/A')  
      app.logger.warning(f"413 Payload Too Large: {request.path}", extra={'request\_id': request\_id})  
      flash("The uploaded file is too large. Maximum size is 16MB.", 'danger')  
      return redirect(request.referrer or url\_for('index\_get'))

  @app.errorhandler(500) \# Generic 500 handler for unhandled exceptions  
  def internal\_server\_error(error): \# error can be Werkzeug Aborter or an unhandled Python exception  
      request\_id \= getattr(g, 'request\_id', 'N/A')  
      app.logger.error(f"Internal Server Error: {error}", exc\_info=True, extra={'request\_id': request\_id})

      original\_message \= "An unexpected internal server error occurred."  
      \# If the error is an instance of our custom error, its original\_exception might have more details  
      if hasattr(error, 'original\_exception') and isinstance(error.original\_exception, COMP5349A2Error):  
          original\_message \= error.original\_exception.message  
      elif isinstance(error, COMP5349A2Error): \# If the error itself is one of ours  
           original\_message \= error.message

      flash(f"An internal server error occurred: {original\_message}. Please try again later.", 'danger')  
      return render\_template('error.html', error\_message=original\_message, error\_code=500, request\_id=request\_id), 500

* **辅助函数 (Helper Function): allowed\_file(filename)**  
  def allowed\_file(filename: str) \-\> bool:  
      """Checks if the filename has an allowed extension."""  
      return '.' in filename and \\  
             filename.rsplit('.', 1)\[1\].lower() in app.config\['ALLOWED\_EXTENSIONS'\]

* **辅助函数 (Helper Function): get\_mime\_type(filename)**  
  def get\_mime\_type(filename: str) \-\> str:  
      """Determines a simple MIME type based on file extension."""  
      ext \= filename.rsplit('.', 1)\[1\].lower()  
      if ext in \['jpg', 'jpeg'\]:  
          return 'image/jpeg'  
      if ext \== 'png':  
          return 'image/png'  
      if ext \== 'gif':  
          return 'image/gif'  
      return 'application/octet-stream' \# Default fallback

#### **Route: GET / (Index/Upload Page)**

* **Unique ID:** COMP5349\_A2-WEB-APPMAIN-index\_get  
* **职责:** 显示包含图片上传表单的主页面。  
* **接口:** HTTP GET 到 /。  
* **前置条件:** 无。  
* **后置条件:** 返回HTTP 200，渲染 index.html 模板。  
* **核心业务逻辑:** 渲染 index.html。  
* **错误处理:** 标准Flask错误处理（例如模板渲染失败）。  
* **日志记录:** INFO: "GET / \- Displaying upload form." (包含 request\_id)。  
* **测试用例:** test\_index\_get\_returns\_200\_and\_renders\_index\_template。

#### **Route: POST /upload**

* **Unique ID:** COMP5349\_A2-WEB-APPMAIN-upload\_post  
* **职责:** 处理图片文件上传，将图片存储到S3，并在RDS中记录初始元数据。  
* **接口:** HTTP POST 到 /upload, enctype="multipart/form-data"。  
* **前置条件:**  
  * 请求包含名为 'file' 的文件部分。  
  * 数据库连接 (g.db\_conn) 可用且有效。  
  * S3桶名 (app.config\['S3\_IMAGE\_BUCKET'\]) 已配置。  
* **后置条件:**  
  * **成功:** 图片上传到S3，元数据保存到RDS。重定向到 /gallery (HTTP 302\) 并显示成功flash消息。  
  * **验证失败 (无文件, 错误类型):** 重新渲染 index.html 并显示错误flash消息 (HTTP 200 或 400，当前选择200并带消息)。  
  * **S3/DB操作失败:** 通过全局错误处理器渲染错误页面或 index.html，并显示错误flash消息。  
* **输入规范 (HTTP请求):**  
  * request.files\['file'\]: 上传的文件 (werkzeug.datastructures.FileStorage)。  
  * 文件大小限制由 app.config\['MAX\_CONTENT\_LENGTH'\] 处理，超出则Flask自动返回413。  
* **输出规范 (HTTP响应):**  
  * **成功:** HTTP 302 到 url\_for('gallery\_get')。Flash消息: "Image '{filename}' uploaded successfully and is being processed."  
  * **无文件/空文件名/无效类型:** 渲染 index.html。Flash消息指明具体错误。  
  * **S3/DB失败:** 由全局错误处理器处理，通常返回500并渲染 error.html。  
* **核心业务逻辑步骤:**  
  1. 记录上传过程开始，包含 g.request\_id。  
  2. 检查 g.db\_conn 是否为 None (来自 before\_request 的失败)。如果是，flash "Database connection error." 并渲染 index.html。  
  3. 验证文件是否存在于 request.files 中。  
  4. 获取文件对象 file \= request.files\['file'\]。  
  5. 验证 file.filename 是否为空。  
  6. 使用 allowed\_file() 验证文件类型。  
  7. 使用 secure\_filename() 清理文件名。  
  8. 生成唯一的 s3\_key: f"{uuid.uuid4().hex}.{filename.rsplit('.', 1)\[1\].lower()}"。记录 s3\_key。  
  9. 使用 get\_mime\_type(filename) 确定 content\_type。  
  10. try...except (S3InteractionError, DatabaseError, InvalidInputError, ConfigurationError) as e:  
      * **Inside try:**  
        * 调用 s3\_utils.upload\_file\_to\_s3(file, app.config\['S3\_IMAGE\_BUCKET'\], s3\_key, content\_type, request\_id=g.request\_id)。 (FileStorage对象通常可以直接传递给 upload\_fileobj，它有 read 方法)。  
        * 调用 db\_utils.save\_initial\_image\_meta(g.db\_conn, s3\_key, request\_id=g.request\_id)。  
        * flash(f"Image '{filename}' uploaded successfully and is being processed.", 'success')。  
        * return redirect(url\_for('gallery\_get'))。  
      * **Inside except e:** (这些自定义异常应由全局错误处理器处理，或者如果希望在此处提供更具体的页面上下文，则局部处理)  
        * app.logger.error(f"Upload failed for {filename}: {e.message}", exc\_info=True, extra={'request\_id': g.request\_id, 'error\_code': getattr(e, 'error\_code', None)})  
        * flash(f"Upload failed: {e.message}", 'danger')  
        * return render\_template('index.html') (或 redirect(url\_for('index\_get')))  
* **交互契约:**  
  * 调用 COMP5349\_A2-UTIL-S3-upload\_file\_to\_s3。  
  * 调用 COMP5349\_A2-UTIL-DB-save\_initial\_image\_meta。  
* **日志记录要求:**  
  * INFO: "POST /upload \- Attempting to upload file: {filename}", request\_id。  
  * INFO: "Generated s3\_key: {s3\_key} for file: {filename}", request\_id。  
  * INFO: "File {filename} (s3\_key: {s3\_key}) uploaded and metadata saved successfully.", request\_id。  
  * ERROR: (如try-except块中所述) "Upload failed for {filename}: {error\_message}", request\_id。  
* **测试用例:**  
  * test\_upload\_post\_successful\_file\_redirects\_to\_gallery\_and\_flashes\_success (mock S3 和 DB utils)  
  * test\_upload\_post\_no\_file\_part\_renders\_index\_with\_error\_flash  
  * test\_upload\_post\_empty\_filename\_renders\_index\_with\_error\_flash  
  * test\_upload\_post\_invalid\_file\_type\_renders\_index\_with\_error\_flash  
  * test\_upload\_post\_s3\_failure\_triggers\_error\_handler (mock s3\_utils.upload\_file\_to\_s3 引发 S3InteractionError)  
  * test\_upload\_post\_db\_failure\_triggers\_error\_handler (mock db\_utils.save\_initial\_image\_meta 引发 DatabaseError)  
  * test\_upload\_post\_db\_connection\_unavailable\_shows\_error (测试 g.db\_conn 为 None 的场景)  
  * test\_upload\_file\_too\_large\_returns\_413 (依赖Flask的 MAX\_CONTENT\_LENGTH 配置)

#### **Route: GET /gallery**

* **Unique ID:** COMP5349\_A2-WEB-APPMAIN-gallery\_get  
* **职责:** 显示所有已上传图片及其当前的标注和缩略图（或状态）。  
* **接口:** HTTP GET 到 /gallery。  
* **前置条件:** 数据库连接 (g.db\_conn) 可用。  
* **后置条件:** 返回HTTP 200，渲染 gallery.html 模板，并填充图片数据。如果获取数据时发生DB/S3错误，则显示错误消息。  
* **输出规范 (HTTP响应):**  
  * **成功:** HTTP 200 OK。渲染 gallery.html。  
  * **传递给模板的数据结构 (processed\_images):** List\[Dict\[str, Any\]\]，每个字典包含：  
    * id: int  
    * original\_s3\_key: str  
    * original\_image\_url: Optional\[str\] (预签名URL)  
    * thumbnail\_s3\_key: Optional\[str\]  
    * thumbnail\_image\_url: Optional\[str\] (预签名URL 或 None)  
    * caption: Optional\[str\] (之前是 caption\_text)  
    * caption\_status: str ('pending', 'completed', 'failed')  
    * thumbnail\_status: str ('pending', 'completed', 'failed')  
    * uploaded\_at: datetime.datetime (Python datetime 对象)  
* **核心业务逻辑步骤:**  
  1. 记录画廊加载开始，包含 g.request\_id。  
  2. 检查 g.db\_conn 是否为 None。如果是，flash "Database connection error." 并渲染 gallery.html，传递 images=\[\] 和错误消息。  
  3. try...except (DatabaseError, S3InteractionError) as e:  
     * **Inside try:**  
       * 调用 image\_records \= db\_utils.get\_all\_image\_data\_for\_gallery(g.db\_conn, request\_id=g.request\_id)。  
       * 初始化空列表 processed\_images \= \[\]。  
       * 遍历 image\_records:  
         * 复制记录到 img\_data。  
         * 设置 img\_data\['original\_image\_url'\] \= None 和 img\_data\['thumbnail\_image\_url'\] \= None 作为默认值。  
         * try...except S3InteractionError as s3\_e\_presign: (针对预签名URL生成失败)  
           * 如果 record\['original\_s3\_key'\] 存在，调用 s3\_utils.generate\_presigned\_url(...) 获取 original\_image\_url。  
           * 如果 record\['thumbnail\_s3\_key'\] 存在且 record\['thumbnail\_status'\] \== 'completed'，调用 s3\_utils.generate\_presigned\_url(...) 获取 thumbnail\_image\_url。  
           * 在 except s3\_e\_presign 中记录错误，对应的URL将保持为 None，模板应能处理此情况。  
         * 将 img\_data 添加到 processed\_images。  
       * 渲染 gallery.html，传递 images=processed\_images。  
     * **Inside except e:** (由全局错误处理器处理)  
       * app.logger.error(f"Failed to load gallery: {e.message}", exc\_info=True, extra={'request\_id': g.request\_id, 'error\_code': getattr(e, 'error\_code', None)})  
       * flash(f"Could not load gallery: {e.message}", 'danger')  
       * return render\_template('gallery.html', images=\[\], error\_message=str(e.message))  
* **交互契约:**  
  * 调用 COMP5349\_A2-UTIL-DB-get\_all\_image\_data\_for\_gallery。  
  * 多次调用 COMP5349\_A2-UTIL-S3-generate\_presigned\_url。  
* **模板交互 (gallery.html):**  
  * 模板需要根据 caption\_status 和 thumbnail\_status 显示不同内容：  
    * pending: 显示 "Processing..." 或占位符。  
    * completed: 显示图片/缩略图和标注。  
    * failed: 显示 "Processing failed" 和错误图标。  
  * 如果 original\_image\_url 或 thumbnail\_image\_url 为 None，显示占位符或错误提示。  
* **日志记录要求:**  
  * INFO: "GET /gallery \- Loading gallery page.", request\_id。  
  * INFO: "Retrieved {len(image\_records)} records from DB for gallery.", request\_id。  
  * INFO: "Successfully prepared {len(processed\_images)} images for gallery display.", request\_id。  
  * ERROR: (如try-except块中所述) "Failed to load gallery: {error\_message}", request\_id。  
  * ERROR: (如果预签名URL失败) "Failed to generate presigned URL for S3 key {key}: {error}", request\_id。  
* **测试用例:**  
  * test\_gallery\_get\_empty\_db\_shows\_no\_images\_message  
  * test\_gallery\_get\_populates\_images\_with\_presigned\_urls\_and\_statuses (mock DB 和 S3 utils)  
  * test\_gallery\_get\_db\_failure\_triggers\_error\_handler  
  * test\_gallery\_get\_s3\_presigned\_url\_failure\_for\_one\_image\_still\_renders\_others\_and\_logs\_error  
  * test\_gallery\_get\_handles\_pending\_and\_failed\_statuses\_correctly\_in\_data\_passed\_to\_template

#### **Route: GET /health (Health Check for ALB)**

* **Unique ID:** COMP5349\_A2-WEB-APPMAIN-health\_get  
* **职责:** 为应用负载均衡器 (ALB) 提供健康检查端点。  
* **接口:** HTTP GET 到 /health。  
* **前置条件:** 无。  
* **后置条件:** 如果应用健康，返回HTTP 200和简单消息 "OK"。如果关键服务（如数据库连接）不可用，返回HTTP 503。  
* **核心业务逻辑步骤:**  
  1. try:  
     * 检查 g.db\_conn 是否为 None (表示 before\_request 中连接失败)。  
     * 如果 g.db\_conn 存在，尝试执行一个轻量级的数据库操作，如 g.db\_conn.ping(reconnect=True, attempts=1, delay=0)。  
     * 如果上述检查通过，返回 "OK", 200。  
  2. except DatabaseError as e: (可能来自 ping 或 before\_request 中 g.db\_conn 为 None 的情况)  
     * app.logger.error(f"Health check failed: DB error \- {e.message}", extra={'request\_id': getattr(g, 'request\_id', 'N/A')})  
     * 返回 "Service Unavailable \- DB Error", 503。  
  3. except Exception as e: (捕获其他意外错误)  
     * app.logger.error(f"Health check failed: Unexpected error \- {str(e)}", exc\_info=True, extra={'request\_id': getattr(g, 'request\_id', 'N/A')})  
     * 返回 "Service Unavailable \- Internal Error", 503。  
* **日志记录要求:**  
  * INFO: "GET /health \- Health check OK." (包含 request\_id)  
  * ERROR: "GET /health \- Health check failed: {reason}." (包含 request\_id)  
* **测试用例:**  
  * test\_health\_check\_db\_ok\_returns\_200  
  * test\_health\_check\_db\_ping\_error\_returns\_503 (mock conn.ping 引发 DatabaseError)  
  * test\_health\_check\_db\_conn\_none\_returns\_503 (模拟 g.db\_conn 为 None)

## **三、Lambda 函数 (lambda\_functions/)**

对于Lambda函数，数据库连接逻辑将与 web\_app/utils/db\_utils.py 中的类似，但会适配Lambda环境（例如，在handler外部初始化一次连接并在多次调用中尝试复用，或每次都新建连接）。它们也将从环境变量读取数据库凭证。为了简单和鲁棒性，可以考虑每次调用都获取新连接，并在 finally 块中关闭。

### **1\. annotation\_lambda/lambda\_function.py**

Module ID: COMP5349\_A2-LAMBDA-ANNOTATION  
Purpose: 由S3对象创建事件触发的AWS Lambda函数。它从S3下载新创建的图像，使用Google Gemini API生成描述性标题，并将此标题和处理状态更新到RDS MySQL数据库中的相应图像记录。

#### **lambda\_handler(event, context)**

* **Unique ID:** COMP5349\_A2-LAMBDA-ANNOTATION-lambda\_handler  
* **职责:** Lambda函数的主入口点。协调S3事件解析、图像下载、通过Gemini API生成标题以及数据库更新的过程。  
* **接口 (事件驱动):**  
  * **触发器:** AWS S3, s3:ObjectCreated:\* 事件。  
  * **输入 (event):** 标准S3事件JSON对象。  
  * **输入 (context):** AWS Lambda上下文对象 (提供运行时信息，如 aws\_request\_id, log\_stream\_name 等)。  
  * **输出:** 返回一个JSON对象，指示成功、跳过或失败，例如 {'status': 'success', 's3\_key': object\_key, 'caption\_generated': True}。此返回值主要用于日志记录/监控。  
* **前置条件:**  
  * Lambda函数具有适当的IAM权限 (S3 GetObject, RDS数据库操作, CloudWatch Logs, Gemini API的网络访问)。  
  * 设置了所需的环境变量：S3\_IMAGE\_BUCKET, GEMINI\_API\_KEY, GEMINI\_MODEL\_NAME, GEMINI\_PROMPT, DB\_HOST, DB\_USER, DB\_PASSWORD, DB\_NAME, DB\_PORT (可选), LOG\_LEVEL。  
  * S3事件结构有效，并包含 Records\[0\].s3.bucket.name 和 Records\[0\].s3.object.key。  
  * 为此Lambda函数配置了死信队列 (SQS)。  
* **后置条件:**  
  * **成功处理:** 生成图像标题，RDS中的 images 表使用标题文本更新，并将对应图像的 caption\_status 设置为 'completed'。  
  * **跳过处理 (例如，缩略图对象):** 不发生S3下载、API调用或数据库更新。Lambda正常退出。  
  * **处理失败 (S3下载、Gemini API、数据库更新):** 记录错误，尝试将RDS中图像的 caption\_status 更新为 'failed' (如果可能，在 caption 字段中记录错误说明)，Lambda可能抛出异常以向S3触发器发出失败信号 (导致重试并最终进入DLQ)。  
* **核心业务逻辑步骤:**  
  1. 初始化日志记录器，从 context 获取 aws\_request\_id。记录执行开始。  
  2. 从S3事件中提取 bucket\_name 和 object\_key。处理潜在的 KeyError 或 IndexError。  
  3. **过滤对象键:** 如果 object\_key.startswith('thumbnails/')，记录INFO并返回 {'status': 'skipped', 'reason': 'thumbnail\_object'}。  
  4. (可选) 增加对文件扩展名的检查，例如只处理 .jpg, .jpeg, .png, .gif 后缀的文件。  
  5. 初始化 db\_conn \= None。  
  6. 使用 try...finally 块确保数据库连接关闭。  
     * try 块内:  
       a. 记录尝试从S3下载图像。  
       b. 调用辅助函数 \_download\_image\_from\_s3(bucket\_name, object\_key, context.aws\_request\_id) 返回 image\_bytes (或抛出 S3InteractionError)。  
       c. 记录尝试调用Gemini API。  
       d. 调用辅助函数 \_call\_gemini\_api(image\_bytes, context.aws\_request\_id) 返回 caption\_text (字符串或 None) 或抛出 GeminiAPIError / ConfigurationError。  
       e. 记录尝试连接数据库。  
       f. db\_conn \= \_get\_db\_connection\_lambda(context.aws\_request\_id) (Lambda特定的数据库连接辅助函数)。  
       g. 如果 caption\_text有效 (非 None 且非空):  
       \* 记录尝试使用成功获取的标题更新数据库。  
       \* 调用辅助函数 \_update\_caption\_in\_db(db\_conn, object\_key, caption\_text, 'completed', context.aws\_request\_id)。  
       \* 记录成功并返回 {'status': 'success', 's3\_key': object\_key, 'caption\_length': len(caption\_text)}。  
       h. 否则 (caption\_text为 None 或空，表示字幕生成问题，如安全阻止或无内容):  
       \* 记录关于无标题的警告/错误。  
       \* 调用 \_update\_caption\_in\_db(db\_conn, object\_key, "Caption generation failed or content was blocked.", 'failed', context.aws\_request\_id)。  
       \* 返回 {'status': 'error', 's3\_key': object\_key, 'error\_type': 'NoCaptionGenerated', 'message': 'Caption generation failed or content was blocked.'}。  
     * **except S3InteractionError as e:** 记录错误。如果 db\_conn 尚未建立，则尝试建立。尝试调用 \_update\_caption\_in\_db 将状态更新为 'failed'。重新抛出异常。  
     * **except GeminiAPIError as e:** 同上，适配Gemini错误。  
     * **except ConfigurationError as e:** (例如 GEMINI\_API\_KEY 缺失) 同上，适配配置错误。  
     * **except DatabaseError as e:** (可能来自 \_get\_db\_connection\_lambda 或 \_update\_caption\_in\_db) 记录严重错误。重新抛出异常。  
     * **except Exception as e:** (捕获所有意外错误) 记录严重未处理异常。如果 db\_conn 已建立，尝试更新状态为 'failed'。包装为 COMP5349A2Error 重新抛出。  
     * **finally 块内:** 如果 db\_conn 非 None 且打开，则调用 db\_conn.close()。记录关闭操作。  
* **错误处理机制:**  
  * 针对S3、Gemini、数据库交互的特定 try-except 块。  
  * 在重新引发严重错误之前，尝试将数据库状态更新为 'failed'。  
  * 依赖AWS Lambda的内置重试机制和后续的DLQ处理。  
* **日志记录要求 (JSON格式，包含 aws\_request\_id):**  
  * INFO: Lambda调用开始，S3事件详情 (bucket, key)。  
  * INFO: 跳过非目标对象 (例如，缩略图)。  
  * DEBUG 或 INFO: 从S3下载图像 (开始、成功、大小)。  
  * DEBUG 或 INFO: Gemini API调用 (开始、成功、标题长度/摘要或阻止原因)。  
  * DEBUG 或 INFO: 数据库连接尝试，数据库更新操作 (开始、成功)。  
  * WARNING: Gemini未生成标题 (例如，安全过滤器)。  
  * ERROR: S3下载失败，Gemini API失败，数据库连接/更新失败 (附带错误详情)。  
  * CRITICAL: 未处理的异常。  
  * INFO: Lambda调用结束 (状态、持续时间)。  
* **测试用例 (使用Mocks进行单元测试):**  
  * test\_handler\_success\_caption\_generated\_and\_db\_updated  
  * test\_handler\_skips\_thumbnail\_object  
  * test\_handler\_s3\_download\_failure\_updates\_db\_status\_to\_failed\_and\_raises  
  * test\_handler\_gemini\_api\_failure\_updates\_db\_status\_to\_failed\_and\_raises  
  * test\_handler\_gemini\_api\_returns\_no\_caption\_updates\_db\_status\_to\_failed  
  * test\_handler\_gemini\_api\_key\_missing\_raises\_config\_error\_and\_updates\_db  
  * test\_handler\_db\_update\_failure\_after\_gemini\_success\_raises\_db\_error  
  * test\_handler\_db\_connection\_failure\_raises\_db\_error  
  * test\_handler\_invalid\_s3\_event\_structure\_logs\_error\_and\_returns\_error\_status  
  * test\_handler\_unexpected\_exception\_updates\_db\_status\_to\_failed\_and\_raises

#### **Helper Function: \_download\_image\_from\_s3(bucket\_name: str, object\_key: str, aws\_request\_id: str) \-\> bytes**

* **Unique ID:** COMP5349\_A2-LAMBDA-ANNOTATION-\_download\_image\_from\_s3  
* **职责:** 从S3下载图像文件并以字节形式返回其内容。  
* **逻辑:** 使用 boto3.client('s3').get\_object()。读取 response\['Body'\]。处理异常并包装为 S3InteractionError。记录日志。

#### **Helper Function: \_call\_gemini\_api(image\_bytes: bytes, aws\_request\_id: str) \-\> Optional\[str\]**

* **Unique ID:** COMP5349\_A2-LAMBDA-ANNOTATION-\_call\_gemini\_api  
* **职责:** 调用Gemini API为给定的图像字节生成标题。  
* **逻辑:**  
  1. 从环境变量获取 GEMINI\_API\_KEY, GEMINI\_MODEL\_NAME, GEMINI\_PROMPT。若 GEMINI\_API\_KEY 缺失，抛出 ConfigurationError。  
  2. 配置 genai.configure(api\_key=...)。  
  3. 创建模型 genai.GenerativeModel(model\_name)。  
  4. **确定MIME类型:** 尝试使用 python-magic 库从 image\_bytes 推断MIME类型。如果库不可用或推断失败，或推断出的类型不在接受列表（如 'image/jpeg', 'image/png', 'image/gif'）中，则默认为 'image/jpeg' 或 'image/png'。  
  5. 构造 image\_part \= {"mime\_type": mime\_type, "data": image\_bytes}。  
  6. 调用 model.generate\_content(\[prompt\_text, image\_part\])。  
  7. 检查 response.prompt\_feedback.block\_reason。如果被阻止，记录警告并返回 None。  
  8. 如果 response.parts 为空或无文本部分，记录警告并返回 None。  
  9. 提取文本 caption \= response.text。  
  10. 记录成功或失败/阻止。  
  11. 返回 caption 或 None。  
  12. 捕获SDK异常并包装为 GeminiAPIError。

#### **Helper Function: \_get\_db\_connection\_lambda(aws\_request\_id: str)**

* **Unique ID:** COMP5349\_A2-LAMBDA-ANNOTATION-\_get\_db\_connection\_lambda  
* **职责:** 使用环境变量建立数据库连接。与 COMP5349\_A2-UTIL-DB-get\_db\_connection 类似，但专为Lambda上下文设计（例如，包含 aws\_request\_id 进行日志记录）。  
* **逻辑:** 读取环境变量，使用 mysql.connector.connect() 连接。在缺少必要环境变量时抛出 ConfigurationError，在连接失败时抛出 DatabaseError。

#### **Helper Function: \_update\_caption\_in\_db(db\_conn, original\_s3\_key: str, caption\_text: Optional\[str\], status: str, aws\_request\_id: str) \-\> bool**

* **Unique ID:** COMP5349\_A2-LAMBDA-ANNOTATION-\_update\_caption\_in\_db  
* **职责:** 在数据库中更新标题和状态。与 COMP5349\_A2-UTIL-DB-update\_caption\_in\_db 类似，但为Lambda日志记录/上下文进行了调整。  
* **逻辑:** 校验状态。执行 UPDATE images SET caption \= %s, caption\_status \= %s WHERE original\_s3\_key \= %s。记录成功/失败。如果 rowcount \> 0 返回 True，否则返回 False。SQL执行失败时抛出 DatabaseError。在日志中包含 aws\_request\_id。

### **2\. thumbnail\_lambda/lambda\_function.py**

Module ID: COMP5349\_A2-LAMBDA-THUMBNAIL  
Purpose: 由S3对象创建事件触发的AWS Lambda函数。它从S3下载新创建的图像，生成固定大小的缩略图（例如，128x128像素，JPEG格式），将缩略图上传到同一S3存储桶内的 thumbnails/ 前缀下，并使用缩略图的S3密钥和处理状态更新RDS MySQL数据库中的相应图像记录。

#### **lambda\_handler(event, context)**

* **Unique ID:** COMP5349\_A2-LAMBDA-THUMBNAIL-lambda\_handler  
* **职责:** Lambda函数的主入口点。协调S3事件解析、图像下载、使用Pillow生成缩略图、将缩略图上传到S3以及数据库更新。  
* **接口 (事件驱动):** 与 annotation\_lambda 相同。  
* **输出:** JSON对象，指示成功、跳过或失败。  
  // Success  
  {"status": "success", "original\_s3\_key": "image.jpg", "thumbnail\_s3\_key": "thumbnails/image.jpg"}  
  // Skipped  
  {"status": "skipped", "s3\_key": "thumbnails/image.jpg", "reason": "Object is already a thumbnail or non-target"}  
  // Failure  
  {"status": "error", "original\_s3\_key": "image.jpg", "error\_type": "ImageProcessingError", "message": "Thumbnail generation failed"}

* **前置条件:**  
  * IAM权限：S3 GetObject (根对象), S3 PutObject (S3\_IMAGE\_BUCKET/thumbnails/\*), RDS操作, CloudWatch Logs。  
  * 环境变量：S3\_IMAGE\_BUCKET, DB\_HOST, DB\_USER, DB\_PASSWORD, DB\_NAME, DB\_PORT (可选), LOG\_LEVEL, THUMBNAIL\_SIZE (e.g., "128x128")。  
  * 已配置DLQ。  
* **后置条件:**  
  * **成功处理:** 缩略图生成并存储在S3的 thumbnails/ 目录下。RDS中的 images 表使用 thumbnail\_s3\_key 更新，并将 thumbnail\_status 设置为 'completed'。  
  * **跳过处理:** 无图像处理或数据库更新。  
  * **处理失败:** 记录错误。尝试将RDS中的 thumbnail\_status 更新为 'failed'。Lambda可能引发异常。  
* **核心业务逻辑步骤:**  
  1. 初始化日志，获取 aws\_request\_id。  
  2. 从S3事件中提取 bucket\_name 和 original\_object\_key。  
  3. **过滤对象键:** 如果 original\_object\_key.startswith('thumbnails/')，记录INFO并返回跳过状态。  
  4. 从环境变量 THUMBNAIL\_SIZE 解析目标尺寸 target\_dims \= (width, height)。如果无效或未设置，则默认为 (128, 128\) 并记录警告。  
  5. 初始化 db\_conn \= None, status\_to\_set \= 'failed', error\_message\_for\_db \= "Unknown error", final\_thumbnail\_s3\_key \= None。  
  6. try...finally (用于数据库连接关闭)。  
     * try 块内:  
       a. 调用 \_download\_image\_from\_s3(...) 获取 image\_bytes。  
       b. 调用 \_generate\_thumbnail(image\_bytes, target\_dims, context.aws\_request\_id) 获取 thumbnail\_bytes\_io (io.BytesIO 对象)。  
       c. 确定缩略图S3 Key:  
       python import os original\_filename\_part \= os.path.basename(original\_object\_key) basename\_without\_ext, \_ \= os.path.splitext(original\_filename\_part) final\_thumbnail\_s3\_key \= f"thumbnails/{basename\_without\_ext}.jpg" \# 输出为JPEG  
       d. 调用 \_upload\_thumbnail\_to\_s3(bucket\_name, final\_thumbnail\_s3\_key, thumbnail\_bytes\_io, context.aws\_request\_id)。  
       e. status\_to\_set \= 'completed'。  
       f. return\_payload \= {'status': 'success', ...}。  
     * **except S3InteractionError as e:** 记录错误，设置 error\_message\_for\_db，return\_payload，重新抛出。  
     * **except ImageProcessingError as e:** 同上。  
     * **except ConfigurationError as e:** (例如 THUMBNAIL\_SIZE 格式错误) 同上。  
     * **except Exception as e:** (意外错误) 记录严重错误，设置 error\_message\_for\_db，return\_payload，包装为 COMP5349A2Error 重新抛出。  
  7. **数据库更新 (在主 try/except 块之后，返回/重新抛出之前):**  
     * try:  
       * db\_conn \= \_get\_db\_connection\_lambda(context.aws\_request\_id)。  
       * 准备 thumbnail\_s3\_key\_for\_db \= final\_thumbnail\_s3\_key if status\_to\_set \== 'completed' else None。  
       * 调用 \_update\_thumbnail\_info\_in\_db(db\_conn, original\_object\_key, thumbnail\_s3\_key\_for\_db, status\_to\_set, context.aws\_request\_id)。  
     * except DatabaseError as db\_e: 记录错误。此时处理可能部分成功，但状态无法更新。  
     * except Exception as db\_e\_unhandled: 记录严重错误。  
     * finally: 关闭 db\_conn。  
  8. 如果在S3/图像处理期间捕获到异常，则重新引发该异常。否则，返回 return\_payload。  
* **错误处理机制:** 与 annotation\_lambda 类似。  
* **日志记录要求 (JSON格式，包含 aws\_request\_id):**  
  * INFO: Lambda开始，S3事件详情，跳过信息。  
  * DEBUG/INFO: 原图下载，缩略图生成 (原始/目标/最终尺寸，格式)，缩略图上传 (key，成功)。  
  * DEBUG/INFO: 数据库连接/更新。  
  * ERROR: 任何步骤中的失败。  
  * CRITICAL: 未处理的异常。  
  * INFO: Lambda结束 (状态，持续时间)。  
* **测试用例 (使用Mocks进行单元测试):**  
  * test\_handler\_success\_thumbnail\_generated\_uploaded\_db\_updated  
  * test\_handler\_skips\_thumbnail\_path\_object  
  * test\_handler\_s3\_download\_failure\_updates\_db\_and\_raises  
  * test\_handler\_image\_processing\_failure\_updates\_db\_and\_raises  
  * test\_handler\_s3\_thumbnail\_upload\_failure\_updates\_db\_and\_raises  
  * test\_handler\_db\_update\_failure\_raises\_db\_error\_after\_processing  
  * test\_handler\_invalid\_thumbnail\_size\_env\_uses\_default\_and\_logs\_warning

#### **Helper Function: \_download\_image\_from\_s3(bucket\_name: str, object\_key: str, aws\_request\_id: str) \-\> bytes**

* **Unique ID:** COMP5349\_A2-LAMBDA-THUMBNAIL-\_download\_image\_from\_s3  
* **注意:** 此函数与 annotation\_lambda 中的功能相同。如果使用Lambda Layers，则可以共享此实用程序。目前，假定它是独立定义的。

#### **Helper Function: \_generate\_thumbnail(image\_bytes: bytes, target\_dims: tuple, aws\_request\_id: str) \-\> io.BytesIO**

* **Unique ID:** COMP5349\_A2-LAMBDA-THUMBNAIL-\_generate\_thumbnail  
* **职责:** 从图像字节生成缩略图，并转换为JPEG格式。  
* **输入:** image\_bytes (bytes), target\_dims (tuple, (width, height))。  
* **逻辑:**  
  1. 记录开始，原始图像字节大小。  
  2. try...except Pillow相关异常:  
     * img \= Image.open(io.BytesIO(image\_bytes))。  
     * 记录原始格式 (img.format) 和尺寸 (img.size)。  
     * **处理透明度 (用于JPEG输出):**  
       if img.mode in ('RGBA', 'LA') or (img.mode \== 'P' and 'transparency' in img.info):  
           \# logger.info(f"Original image mode {img.mode} has alpha, converting to RGB with white background.", ...)  
           background \= Image.new('RGB', img.size, (255, 255, 255))  
           img\_to\_paste \= img.convert('RGBA') if img.mode \== 'P' and 'transparency' in img.info else img \# Ensure alpha channel for paste  
           background.paste(img\_to\_paste, (0,0), img\_to\_paste if img\_to\_paste.mode \== 'RGBA' else img\_to\_paste.convert('RGBA'))  
           img \= background  
       elif img.mode \!= 'RGB':  
           \# logger.info(f"Original image mode {img.mode}, converting to RGB.", ...)  
           img \= img.convert('RGB')

     * img.thumbnail(target\_dims, Image.Resampling.LANCZOS) (原地修改 img)。  
     * 创建 output\_io \= io.BytesIO()。  
     * img.save(output\_io, format='JPEG', quality=85) (quality可调，85是不错的起点)。  
     * output\_io.seek(0)。  
     * 记录INFO: "Thumbnail generated. New size: {img.size}, Output format: JPEG."。  
     * 返回 output\_io。  
  3. except UnidentifiedImageError as uie: 记录错误。抛出 ImageProcessingError(message=f"Cannot identify image file: {uie}", ..., error\_code="INVALID\_IMAGE\_FORMAT")。  
  4. except Exception as e: (其他Pillow错误) 记录错误。抛出 ImageProcessingError(message=f"Pillow processing error: {e}", ..., error\_code="PILLOW\_PROCESSING\_ERROR")。

#### **Helper Function: \_upload\_thumbnail\_to\_s3(bucket\_name: str, thumbnail\_s3\_key: str, thumbnail\_bytes\_io: io.BytesIO, aws\_request\_id: str)**

* **Unique ID:** COMP5349\_A2-LAMBDA-THUMBNAIL-\_upload\_thumbnail\_to\_s3  
* **职责:** 将生成的缩略图 (JPEG) 上传到S3。  
* **逻辑:** 使用 boto3.client('s3').upload\_fileobj()，在 ExtraArgs 中设置 ContentType='image/jpeg'。处理异常并包装为 S3InteractionError。记录日志。

#### **Helper Function: \_get\_db\_connection\_lambda(aws\_request\_id: str)**

* **Unique ID:** COMP5349\_A2-LAMBDA-THUMBNAIL-\_get\_db\_connection\_lambda  
* **注意:** 与 annotation\_lambda 中的相同。

#### **Helper Function: \_update\_thumbnail\_info\_in\_db(db\_conn, original\_s3\_key: str, thumbnail\_s3\_key: Optional\[str\], status: str, aws\_request\_id: str) \-\> bool**

* **Unique ID:** COMP5349\_A2-LAMBDA-THUMBNAIL-\_update\_thumbnail\_info\_in\_db  
* **职责:** 在数据库中更新缩略图S3密钥和状态。  
* **逻辑:** 与 COMP5349\_A2-UTIL-DB-update\_thumbnail\_info\_in\_db / annotation\_lambda.\_update\_caption\_in\_db 类似。

## **四、数据库 (database/)**

### **schema.sql (或 create-database.sh 中的SQL部分) \- 最终确认**

Module ID: COMP5349\_A2-DB\_SCRIPT-SCHEMA  
Purpose: 定义 images 表的SQL模式，该表用于存储已上传图像的元数据，包括其S3位置、生成的标题、缩略图位置和处理状态。此模式旨在支持Assignment 2的异步处理特性。

#### **表: images**

* **职责:** 存储与每个已上传图像相关的所有元数据。  
* **Schema 定义:**  
  CREATE TABLE IF NOT EXISTS images (  
      id INT AUTO\_INCREMENT PRIMARY KEY,  
      original\_s3\_key VARCHAR(1024) NOT NULL UNIQUE, \-- 原始上传图像的完整S3对象键。S3键最大长度为1024字节。  
      caption TEXT NULL,                             \-- 由 annotation Lambda 生成的标题。可为空。  
      thumbnail\_s3\_key VARCHAR(1024) NULL,           \-- 生成的缩略图的完整S3对象键 (例如, 'thumbnails/your\_image.jpg')。可为空。  
      caption\_status VARCHAR(20) NOT NULL DEFAULT 'pending', \-- 标题生成状态: 'pending', 'completed', 'failed'。  
      thumbnail\_status VARCHAR(20) NOT NULL DEFAULT 'pending', \-- 缩略图生成状态: 'pending', 'completed', 'failed'。  
      uploaded\_at TIMESTAMP NOT NULL DEFAULT CURRENT\_TIMESTAMP, \-- 初始上传的时间戳。

      \-- 性能索引  
      INDEX idx\_uploaded\_at (uploaded\_at DESC),      \-- 用于画廊排序  
      INDEX idx\_caption\_status (caption\_status),     \-- 用于按标题状态查询图像  
      INDEX idx\_thumbnail\_status (thumbnail\_status)  \-- 用于按缩略图状态查询图像  
  ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4\_unicode\_ci;

* **字段解释和决策:**  
  * id: 标准自增主键。  
  * original\_s3\_key: 存储原始图像的唯一S3键。VARCHAR(1024) 以适应S3的最大键长。NOT NULL UNIQUE 至关重要。  
  * caption: 存储由 annotation\_lambda 生成的文本。TEXT 允许长标题。可为空，因为它是异步填充的。  
  * thumbnail\_s3\_key: 存储生成的缩略图的唯一S3键 (例如 thumbnails/some\_uuid.jpg)。VARCHAR(1024)。可为空。  
  * caption\_status: VARCHAR(20) 足以容纳 'pending', 'completed', 'failed'。NOT NULL DEFAULT 'pending'。  
  * thumbnail\_status: VARCHAR(20)，逻辑同 caption\_status。NOT NULL DEFAULT 'pending'。  
  * uploaded\_at: TIMESTAMP NOT NULL DEFAULT CURRENT\_TIMESTAMP 用于记录上传时间，对画廊排序至关重要。  
* **索引:**  
  * original\_s3\_key 上的 UNIQUE 约束会自动创建索引。  
  * idx\_uploaded\_at (uploaded\_at DESC): 对于高效获取画廊视图的图像（按上传时间排序）至关重要。  
  * idx\_caption\_status 和 idx\_thumbnail\_status: 对于未来可能的管理任务或仪表板（例如，查找所有字幕生成失败的图像）非常有用。  
* **引擎和字符集:** ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4\_unicode\_ci 是MySQL的标准良好选择，支持广泛的字符（对标题很重要）和事务。  
* **与作业要求的符合度:**  
  * 此模式直接支持存储原始图像位置、生成的标题、生成的缩略图及其各自的处理状态，这些都是Web应用程序的画廊页面和Lambda函数操作所必需的。  
  * 它将Web应用程序与标题和缩略图的直接生成解耦，符合无服务器架构的要求。  
* **create-database.sh 调整:**  
  * 来自Assignment 1的 create-database.sh 脚本需要更新，以反映这个新的 images 表模式，而不是旧的 captions 表。

## **五、部署 (deployment/)**

Module ID: COMP5349\_A2-DEPLOYMENT-ARCHITECTURE  
Purpose: 概述部署整个图像标注系统的关键AWS资源及其配置策略。本节作为创建CloudFormation模板或Terraform脚本的蓝图。目标是实现云计算项目所期望的可扩展、有弹性且经济高效的架构。

### **关键AWS资源与配置策略**

1. **VPC (Virtual Private Cloud):**  
   * **CIDR块:** 例如 10.0.0.0/16。  
   * **子网 (Subnets):**  
     * **公共子网 (Public Subnets):** 至少两个，位于不同的可用区 (AZ)，以实现高可用性 (例如 10.0.1.0/24, 10.0.2.0/24)。用于ALB、NAT网关、堡垒主机 (可选)。  
     * **私有子网 (Private Subnets):** 至少两个，位于不同的AZ (例如 10.0.101.0/24, 10.0.102.0/24)。用于EC2实例 (Web应用)、RDS实例和Lambda函数 (如果需要在VPC内访问RDS)。  
   * **路由表 (Route Tables):**  
     * **公共路由表:** 路由到互联网网关 (IGW) 的 0.0.0.0/0。  
     * **私有路由表 (每个AZ一个或共享):** 路由到NAT网关 (位于同一AZ) 的 0.0.0.0/0。  
   * **互联网网关 (IGW):** 附加到VPC。  
   * **NAT网关 (NAT Gateways):**  
     * 在公共子网中每个AZ一个NAT网关 (带有弹性IP地址) 以实现高可用性，或者为了本作业节省成本而使用单个NAT网关。  
     * **决策:** 为Learner Lab的成本效益起见，从一个NAT网关开始，并承认高可用性方案会使用更多。  
2. **安全组 (Security Groups \- SG):**  
   * ALBSecurityGroup: 入站允许来自 0.0.0.0/0 的HTTP (80) (和HTTPS 443，如果配置)。出站允许到 EC2InstanceSecurityGroup 的Flask应用端口 (例如5000)。  
   * EC2InstanceSecurityGroup: 入站允许来自 ALBSecurityGroup 的Flask应用端口。入站允许来自特定堡垒主机SG或可信IP范围的SSH (22) (用于开发/调试)。出站允许到 RDSSecurityGroup 的MySQL端口 (3306)，以及通过NAT网关访问互联网 (例如，用于包下载的HTTPS/443，调用外部API)。  
   * RDSSecurityGroup: 入站允许来自 EC2InstanceSecurityGroup 和 LambdaSecurityGroup (如果Lambda在VPC内) 的MySQL端口 (3306)。除非有特定的数据库功能需求，否则不需要出站规则。  
   * LambdaSecurityGroup (如果Lambda函数启用VPC以访问RDS): 不需要特定的入站规则 (Lambda服务管理此项)。出站允许到 RDSSecurityGroup 的MySQL端口 (3306)，以及通过NAT网关访问互联网 (例如，用于Gemini API的HTTPS/443)。  
3. **IAM角色和策略 (IAM Roles and Policies):**  
   * EC2InstanceProfileRole:  
     * S3权限: s3:PutObject, s3:GetObject, s3:ListBucket (如果应用需要) 限制到 arn:aws:s3:::{S3\_IMAGE\_BUCKET}/\*。  
     * CloudWatch Logs权限: logs:CreateLogStream, logs:PutLogEvents 到特定的日志组。  
     * (如果使用Secrets Manager) 从AWS Secrets Manager读取数据库凭证的权限。  
   * AnnotationLambdaExecutionRole:  
     * AWSLambdaBasicExecutionRole (用于CloudWatch Logs)。  
     * AWSLambdaVPCAccessExecutionRole (如果在VPC内)。  
     * S3权限: s3:GetObject 来自 arn:aws:s3:::{S3\_IMAGE\_BUCKET}/\*。  
     * RDS: (如果在VPC内) 通过安全组进行网络访问。数据库凭证通过环境变量提供 (最好来自Secrets Manager)。  
     * (如果使用Secrets Manager) 读取权限。  
     * (隐式) Gemini API的网络访问权限 (通过NAT网关)。  
   * ThumbnailLambdaExecutionRole:  
     * AWSLambdaBasicExecutionRole, AWSLambdaVPCAccessExecutionRole (如果需要)。  
     * S3权限: s3:GetObject 来自 arn:aws:s3:::{S3\_IMAGE\_BUCKET}/\*, s3:PutObject 到 arn:aws:s3:::{S3\_IMAGE\_BUCKET}/thumbnails/\*。  
     * RDS & Secrets Manager: 与 AnnotationLambdaExecutionRole 类似。  
4. **S3存储桶 (S3\_IMAGE\_BUCKET 变量):**  
   * **名称:** 全局唯一 (例如 comp5349-a2-images-\<your-unique-id\>)。  
   * **版本控制:** 禁用 (为简单和成本考虑，默认为禁用)。  
   * **事件通知:**  
     * **事件类型:** s3:ObjectCreated:\*。  
     * **前缀过滤器:** 无 (Lambda代码将过滤 thumbnails/ 下的对象)。或者，可以配置前缀，例如只对 uploads/ 前缀触发。当前设计是Lambda内部过滤 thumbnails/。  
     * **后缀过滤器:** .jpg, .jpeg, .png, .gif (以避免对其他文件类型触发)。  
     * **目标:** annotation\_lambda 的ARN **和** thumbnail\_lambda 的ARN (一个S3事件通知可以触发多个Lambda函数)。  
5. **RDS MySQL实例:**  
   * **引擎:** MySQL (例如 8.0.x)。  
   * **实例类别:** 最小适用实例 (例如 Learner Lab中的 db.t3.micro 或 db.t2.micro)。  
   * **存储:** 例如 20GB SSD (gp2/gp3)。  
   * **多可用区 (Multi-AZ):** 禁用 (为Learner Lab成本考虑)。  
   * **数据库名称:** 来自 DB\_NAME 环境变量的值 (例如 image\_annotation\_db)。  
   * **主用户名/密码:** 通过AWS Secrets Manager管理。Lambda/EC2的IAM角色将有权获取这些密钥。这是最佳实践。如果因设置简单性而未使用Secrets Manager，则在RDS创建期间设置凭证，并通过安全的环境变量传递。**决策：** 如果设置允许，目标是使用Secrets Manager，否则使用安全的环境变量。  
   * **VPC子网组:** 指向私有子网。  
   * **安全组:** RDSSecurityGroup。  
   * **公共可访问性:** 否。  
6. **EC2 Auto Scaling Group (ASG) & 启动模板/配置 (Launch Template/Configuration):**  
   * **启动模板:**  
     * **AMI ID:** 最新的Amazon Linux 2或Ubuntu LTS。  
     * **实例类型:** 例如 t3.micro。  
     * **IAM实例配置文件:** EC2InstanceProfileRole。  
     * **密钥对:** (用于开发/调试期间的SSH访问，如果需要)。  
     * **安全组:** EC2InstanceSecurityGroup。  
     * **用户数据脚本 (User Data Script):**  
       * 安装Python 3.9, pip。  
       * 安装系统依赖项 (例如 mysql-devel 或 libmysqlclient-dev，如果任何Python数据库驱动程序需要编译，尽管 mysql-connector-python 通常不需要)。  
       * 设置环境变量 (例如，通过加载文件，或更好地从Secrets Manager或SSM Parameter Store获取)。  
       * 创建应用程序目录，克隆/复制Web应用代码。  
       * 从 web\_app/requirements.txt 安装Python依赖项。  
       * (可选，取决于部署策略) 运行数据库模式创建/迁移脚本 (create-database.sh 或Python迁移工具)。最好单独运行数据库设置或从CodeDeploy钩子运行。对于此作业，假定在ASG启动前手动或通过单独脚本设置模式一次，或者应用程序具有容错性。  
       * 使用Gunicorn启动Flask应用程序 (例如 gunicorn \--bind 0.0.0.0:5000 app:app)。  
   * **ASG配置:**  
     * **最小/期望/最大实例数:** Min=1, Desired=1 (初始状态), Max=3 (根据要求 "maximum capacity greater than 1 instance")。  
     * **目标组:** 与ALB的目标组关联。  
     * **可用区:** 跨越至少两个AZ中的私有子网。  
     * **扩展策略:** 基于平均CPU利用率的目标跟踪 (例如，如果CPU \> 70%则扩展，如果CPU \< 30%则收缩)。冷却时间 (例如300秒)。  
7. **Application Load Balancer (ALB):**  
   * **方案 (Scheme):** 面向互联网 (Internet-facing)。  
   * **侦听器 (Listeners):** HTTP 端口 80。(可选：HTTPS 443，需要ACM证书，并将HTTP重定向到HTTPS)。作业要求通常不强制HTTPS，先用HTTP 80。  
   * **规则 (Rules):** 将请求转发到一个目标组。  
   * **目标组 (Target Group):**  
     * **目标类型:** Instance。  
     * **协议:** HTTP。  
     * **端口:** Flask应用端口 (例如5000)。  
     * **健康检查 (Health Check):** HTTP GET到Flask应用端口上的 /health。期望HTTP 200。配置健康/不健康阈值、间隔、超时。  
     * **VPC & 子网:** 公共子网。  
     * **安全组:** ALBSecurityGroup。  
8. **Lambda 函数 (annotation\_lambda, thumbnail\_lambda):**  
   * **运行时 (Runtime):** python3.9。  
   * **处理程序 (Handler):** 例如 lambda\_function.lambda\_handler。  
   * **内存 (Memory):** 例如 256MB或512MB (根据Pillow/Gemini SDK使用情况进行调整)。  
   * **超时 (Timeout):** 例如60秒 (根据Gemini API响应时间和图像处理时间进行调整)。  
   * **环境变量:** 如前所述 (数据库凭证/ARN，S3桶，Gemini密钥/配置，LOG\_LEVEL，THUMBNAIL\_SIZE)。  
   * **IAM角色:** 各自的执行角色 (AnnotationLambdaExecutionRole, ThumbnailLambdaExecutionRole)。  
   * **VPC配置 (如果访问VPC内的RDS):** 私有子网ID列表，LambdaSecurityGroup ID列表。  
   * **死信队列 (DLQ):** 一个SQS队列的ARN。  
   * **S3触发器:** 在S3桶上配置 (见S3部分)。  
9. **SQS队列 (用于DLQ):**  
   * 一个SQS标准队列 (例如 ImageProcessingDLQ) 用于接收失败的Lambda调用。  
   * (可选) 如果 ApproximateNumberOfMessagesVisible \> 0 持续一段时间，则配置CloudWatch警报。  
10. **(可选) AWS Secrets Manager:**  
    * 存储RDS主密码，Gemini API密钥。  
    * EC2和Lambda的IAM角色将有权读取这些密钥。