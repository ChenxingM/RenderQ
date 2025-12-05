/**
 * RenderQ - After Effects 提交面板
 * 可停靠的 ScriptUI 面板，用于向 RenderQ 服务器提交渲染任务
 */

(function(thisObj) {
    // ============ 配置 ============
    var CONFIG = {
        serverUrl: "http://localhost:8000",
        scriptName: "RenderQ",
        version: "1.0.0"
    };

    // ============ 工具函数 ============

    /**
     * 发送 HTTP 请求到 RenderQ 服务器
     */
    function httpRequest(method, endpoint, data) {
        var url = CONFIG.serverUrl + endpoint;
        var response = null;

        try {
            // 使用 system.callSystem 调用 curl (Windows/Mac)
            var jsonData = data ? JSON.stringify(data) : "";
            var cmd;

            if ($.os.indexOf("Windows") !== -1) {
                // Windows - 使用 curl
                jsonData = jsonData.replace(/"/g, '\\"');
                if (method === "GET") {
                    cmd = 'curl -s -X GET "' + url + '"';
                } else {
                    cmd = 'curl -s -X ' + method + ' -H "Content-Type: application/json" -d "' + jsonData + '" "' + url + '"';
                }
            } else {
                // macOS/Linux
                if (method === "GET") {
                    cmd = "curl -s -X GET '" + url + "'";
                } else {
                    cmd = "curl -s -X " + method + " -H 'Content-Type: application/json' -d '" + jsonData + "' '" + url + "'";
                }
            }

            response = system.callSystem(cmd);

            if (response) {
                return JSON.parse(response);
            }
        } catch (e) {
            alert("HTTP 请求失败: " + e.message + "\n响应: " + response);
        }

        return null;
    }

    /**
     * 获取当前工程的合成列表
     */
    function getCompositions() {
        var comps = [];
        var project = app.project;

        if (!project) return comps;

        for (var i = 1; i <= project.numItems; i++) {
            var item = project.item(i);
            if (item instanceof CompItem) {
                comps.push({
                    name: item.name,
                    width: item.width,
                    height: item.height,
                    frameRate: item.frameRate,
                    duration: item.duration,
                    numFrames: Math.floor(item.duration * item.frameRate)
                });
            }
        }

        return comps;
    }

    /**
     * 检测输出类型
     */
    function detectOutputType(filePath, format) {
        if (!filePath) return "unknown";

        // 检测是否是序列 (包含 [#####] 或类似模式)
        if (filePath.match(/\[#+\]/) || filePath.match(/_\d{5}\./) || filePath.match(/\.\d{5}\./)) {
            return "sequence";
        }

        // 检测常见视频格式
        var videoExts = [".mov", ".mp4", ".avi", ".mkv", ".m4v", ".wmv"];
        var imageExts = [".png", ".jpg", ".jpeg", ".tif", ".tiff", ".psd", ".exr", ".dpx"];

        var ext = filePath.toLowerCase().match(/\.[^.]+$/);
        if (ext) {
            ext = ext[0];
            if (videoExts.indexOf(ext) !== -1) return "video";
            if (imageExts.indexOf(ext) !== -1) return "single_image";
        }

        // 根据格式判断
        var formatLower = format.toLowerCase();
        if (formatLower.indexOf("sequence") !== -1) return "sequence";
        if (formatLower.indexOf("quicktime") !== -1 || formatLower.indexOf("h.264") !== -1) return "video";

        return "unknown";
    }

    /**
     * 获取渲染队列项目
     */
    function getRenderQueueItems() {
        var items = [];
        var rq = app.project.renderQueue;

        for (var i = 1; i <= rq.numItems; i++) {
            var rqItem = rq.item(i);
            if (rqItem.status === RQItemStatus.QUEUED) {
                var comp = rqItem.comp;
                var outputModules = [];
                var hasPngSequence = false;
                var hasVideoOutput = false;

                for (var j = 1; j <= rqItem.numOutputModules; j++) {
                    var om = rqItem.outputModule(j);
                    var filePath = om.file ? om.file.fsName : "";
                    var outputType = detectOutputType(filePath, om.format || "");

                    // 检测是否有 PNG 序列输出
                    if (outputType === "sequence" && filePath.toLowerCase().indexOf(".png") !== -1) {
                        hasPngSequence = true;
                    }
                    // 检测是否有视频输出
                    if (outputType === "video") {
                        hasVideoOutput = true;
                    }

                    outputModules.push({
                        index: j,
                        file: filePath,
                        format: om.format,
                        outputType: outputType
                    });
                }

                // 计算帧信息 - 使用渲染队列项目的时间范围，而非合成的工作区
                var frameRate = comp.frameRate;
                var duration = rqItem.timeSpanDuration;
                var startFrame = Math.floor(rqItem.timeSpanStart * frameRate);
                var endFrame = Math.floor((rqItem.timeSpanStart + rqItem.timeSpanDuration) * frameRate);
                // 确保至少1帧
                if (endFrame > startFrame) {
                    endFrame = endFrame - 1;
                }
                var totalFrames = endFrame - startFrame + 1;

                // 检测是否是单帧渲染
                var isSingleFrame = (totalFrames <= 1) || (startFrame === endFrame) || (rqItem.timeSpanDuration <= (1 / frameRate));

                items.push({
                    index: i,
                    compName: comp.name,
                    status: "queued",
                    outputModules: outputModules,
                    // 帧信息
                    frameStart: startFrame,
                    frameEnd: endFrame,
                    totalFrames: totalFrames,
                    frameRate: frameRate,
                    width: comp.width,
                    height: comp.height,
                    duration: duration,
                    // 类型检测
                    isSingleFrame: isSingleFrame,
                    hasPngSequence: hasPngSequence,
                    hasVideoOutput: hasVideoOutput
                });
            }
        }

        return items;
    }

    /**
     * 保存工程文件
     */
    function saveProject() {
        if (!app.project.file) {
            alert("请先保存工程文件");
            return null;
        }
        app.project.save();
        return app.project.file.fsName;
    }

    // ============ UI 构建 ============

    function buildUI(thisObj) {
        var panel = (thisObj instanceof Panel)
            ? thisObj
            : new Window("palette", CONFIG.scriptName, undefined, {resizeable: true});

        panel.orientation = "column";
        panel.alignChildren = ["fill", "top"];
        panel.spacing = 10;
        panel.margins = 10;

        // ---- 服务器配置 ----
        var serverGroup = panel.add("panel", undefined, "服务器配置");
        serverGroup.alignChildren = ["fill", "center"];
        serverGroup.margins = 10;

        var urlGroup = serverGroup.add("group");
        urlGroup.add("statictext", undefined, "地址:");
        var serverUrlInput = urlGroup.add("edittext", undefined, CONFIG.serverUrl);
        serverUrlInput.characters = 25;

        var connectBtn = serverGroup.add("button", undefined, "测试连接");
        var statusText = serverGroup.add("statictext", undefined, "状态: 未连接");
        statusText.graphics.foregroundColor = statusText.graphics.newPen(
            statusText.graphics.PenType.SOLID_COLOR, [0.7, 0.7, 0.7], 1
        );

        // ---- 模式选择 ----
        var modeGroup = panel.add("panel", undefined, "提交模式");
        modeGroup.alignChildren = ["fill", "center"];
        modeGroup.margins = 10;

        var modeRadio1 = modeGroup.add("radiobutton", undefined, "模式1: 渲染队列");
        var modeRadio2 = modeGroup.add("radiobutton", undefined, "模式2: 指定合成");
        modeRadio1.value = true;

        // ---- 模式1: 渲染队列 ----
        var mode1Panel = panel.add("panel", undefined, "渲染队列");
        mode1Panel.alignChildren = ["fill", "center"];
        mode1Panel.margins = 10;

        var rqListBox = mode1Panel.add("listbox", undefined, [], {
            multiselect: true,
            numberOfColumns: 2,
            showHeaders: true,
            columnTitles: ["合成", "输出"]
        });
        rqListBox.preferredSize = [300, 120];

        var refreshRqBtn = mode1Panel.add("button", undefined, "刷新队列");

        // ---- 模式2: 指定合成 ----
        var mode2Panel = panel.add("panel", undefined, "指定合成渲染");
        mode2Panel.alignChildren = ["fill", "center"];
        mode2Panel.margins = 10;

        // 合成选择
        var compGroup = mode2Panel.add("group");
        compGroup.add("statictext", undefined, "合成:");
        var compDropdown = compGroup.add("dropdownlist", undefined, []);
        compDropdown.preferredSize = [200, 25];

        var refreshCompBtn = compGroup.add("button", undefined, "刷新");
        refreshCompBtn.preferredSize = [50, 25];

        // 帧范围
        var frameGroup = mode2Panel.add("group");
        frameGroup.add("statictext", undefined, "帧范围:");
        var frameStartInput = frameGroup.add("edittext", undefined, "0");
        frameStartInput.characters = 6;
        frameGroup.add("statictext", undefined, "-");
        var frameEndInput = frameGroup.add("edittext", undefined, "100");
        frameEndInput.characters = 6;
        var useCompRangeCheck = frameGroup.add("checkbox", undefined, "使用合成设置");
        useCompRangeCheck.value = true;

        // 输出格式
        var formatGroup = mode2Panel.add("group");
        formatGroup.alignment = ["fill", "center"];
        formatGroup.add("statictext", undefined, "输出格式:");
        var formatPngCheck = formatGroup.add("checkbox", undefined, "PNG");
        var format4444Check = formatGroup.add("checkbox", undefined, "ProRes 4444");
        var formatMp4Check = formatGroup.add("checkbox", undefined, "MP4");
        formatPngCheck.value = true;

        // 输出路径
        var outputGroup = mode2Panel.add("group");
        outputGroup.alignment = ["fill", "center"];
        outputGroup.add("statictext", undefined, "输出目录:");
        var outputPathInput = outputGroup.add("edittext", undefined, "");
        outputPathInput.characters = 20;
        var browseBtn = outputGroup.add("button", undefined, "...");
        browseBtn.preferredSize = [30, 25];

        // ---- 任务选项 ----
        var optionsPanel = panel.add("panel", undefined, "任务选项");
        optionsPanel.alignChildren = ["fill", "center"];
        optionsPanel.margins = 10;

        var nameGroup = optionsPanel.add("group");
        nameGroup.add("statictext", undefined, "任务名称:");
        var jobNameInput = nameGroup.add("edittext", undefined, "");
        jobNameInput.characters = 20;

        var priorityGroup = optionsPanel.add("group");
        priorityGroup.add("statictext", undefined, "优先级:");
        var prioritySlider = priorityGroup.add("slider", undefined, 50, 0, 100);
        var priorityText = priorityGroup.add("statictext", undefined, "50");
        priorityText.characters = 3;

        // ---- 提交按钮 ----
        var submitBtn = panel.add("button", undefined, "提交任务");
        submitBtn.preferredSize = [0, 35];

        // ============ 事件处理 ============

        // 模式切换
        function updateModeVisibility() {
            mode1Panel.visible = modeRadio1.value;
            mode2Panel.visible = modeRadio2.value;
            panel.layout.layout(true);
        }

        modeRadio1.onClick = updateModeVisibility;
        modeRadio2.onClick = updateModeVisibility;

        // 测试连接
        connectBtn.onClick = function() {
            CONFIG.serverUrl = serverUrlInput.text;
            var result = httpRequest("GET", "/api/stats");
            if (result) {
                statusText.text = "状态: 已连接";
                statusText.graphics.foregroundColor = statusText.graphics.newPen(
                    statusText.graphics.PenType.SOLID_COLOR, [0.2, 0.8, 0.2], 1
                );
            } else {
                statusText.text = "状态: 连接失败";
                statusText.graphics.foregroundColor = statusText.graphics.newPen(
                    statusText.graphics.PenType.SOLID_COLOR, [0.8, 0.2, 0.2], 1
                );
            }
        };

        // 刷新渲染队列
        refreshRqBtn.onClick = function() {
            rqListBox.removeAll();
            var items = getRenderQueueItems();
            for (var i = 0; i < items.length; i++) {
                var item = items[i];
                var output = item.outputModules.length > 0 ? item.outputModules[0].file : "(未设置)";

                // 显示帧数信息，标记单帧
                var frameInfo;
                if (item.isSingleFrame) {
                    frameInfo = item.compName + " [单帧:" + item.frameStart + "]";
                } else {
                    frameInfo = item.compName + " [" + item.frameStart + "-" + item.frameEnd + "] (" + item.totalFrames + "f)";
                }

                var listItem = rqListBox.add("item", frameInfo);
                listItem.subItems[0].text = output;
                listItem.rqData = item;
            }
        };

        // 刷新合成列表
        function refreshCompositions() {
            compDropdown.removeAll();
            var comps = getCompositions();
            for (var i = 0; i < comps.length; i++) {
                var item = compDropdown.add("item", comps[i].name);
                item.compData = comps[i];
            }
            if (comps.length > 0) {
                compDropdown.selection = 0;
                updateFrameRange();
            }
        }

        refreshCompBtn.onClick = refreshCompositions;

        // 更新帧范围
        function updateFrameRange() {
            if (useCompRangeCheck.value && compDropdown.selection) {
                var compData = compDropdown.selection.compData;
                frameStartInput.text = "0";
                frameEndInput.text = String(compData.numFrames - 1);
                frameStartInput.enabled = false;
                frameEndInput.enabled = false;
            } else {
                frameStartInput.enabled = true;
                frameEndInput.enabled = true;
            }
        }

        compDropdown.onChange = updateFrameRange;
        useCompRangeCheck.onClick = updateFrameRange;

        // 优先级滑块
        prioritySlider.onChanging = function() {
            priorityText.text = String(Math.round(prioritySlider.value));
        };

        // 浏览输出目录
        browseBtn.onClick = function() {
            var folder = Folder.selectDialog("选择输出目录");
            if (folder) {
                outputPathInput.text = folder.fsName;
            }
        };

        // 提交任务
        submitBtn.onClick = function() {
            CONFIG.serverUrl = serverUrlInput.text;

            // 保存工程
            var projectPath = saveProject();
            if (!projectPath) return;

            var jobName = jobNameInput.text || app.project.file.name.replace(/\.aep$/i, "");
            var priority = Math.round(prioritySlider.value);

            if (modeRadio1.value) {
                // 模式1: 渲染队列
                submitRenderQueueMode(projectPath, jobName, priority, rqListBox);
            } else {
                // 模式2: 指定合成
                submitCustomRenderMode(projectPath, jobName, priority, {
                    comp: compDropdown.selection ? compDropdown.selection.compData : null,
                    frameStart: parseInt(frameStartInput.text, 10),
                    frameEnd: parseInt(frameEndInput.text, 10),
                    outputPng: formatPngCheck.value,
                    outputProRes: format4444Check.value,
                    outputMp4: formatMp4Check.value,
                    outputPath: outputPathInput.text
                });
            }
        };

        // 初始化
        updateModeVisibility();
        refreshCompositions();
        refreshRqBtn.onClick();

        // 面板调整
        panel.onResizing = panel.onResize = function() {
            this.layout.resize();
        };

        if (panel instanceof Window) {
            panel.center();
            panel.show();
        } else {
            panel.layout.layout(true);
        }

        return panel;
    }

    // ============ 提交逻辑 ============

    /**
     * 模式1: 提交渲染队列 (直接渲染AE队列，不拆分)
     */
    function submitRenderQueueMode(projectPath, jobName, priority, rqListBox) {
        var selectedItems = rqListBox.selection;
        if (!selectedItems || selectedItems.length === 0) {
            alert("请选择要渲染的队列项目");
            return;
        }

        // 收集选中的渲染队列项目信息
        var rqItems = [];
        var totalFrames = 0;
        for (var i = 0; i < selectedItems.length; i++) {
            var rqData = selectedItems[i].rqData;

            // 收集输出模块信息
            var outputModules = [];
            for (var j = 0; j < rqData.outputModules.length; j++) {
                outputModules.push({
                    index: rqData.outputModules[j].index,
                    file: rqData.outputModules[j].file,
                    format: rqData.outputModules[j].format,
                    output_type: rqData.outputModules[j].outputType
                });
            }

            rqItems.push({
                index: rqData.index,
                comp_name: rqData.compName,
                frame_start: rqData.frameStart,
                frame_end: rqData.frameEnd,
                total_frames: rqData.totalFrames,
                frame_rate: rqData.frameRate,
                width: rqData.width,
                height: rqData.height,
                output_path: rqData.outputModules.length > 0 ? rqData.outputModules[0].file : "",
                output_modules: outputModules,
                // 类型标记
                is_single_frame: rqData.isSingleFrame,
                has_png_sequence: rqData.hasPngSequence,
                has_video_output: rqData.hasVideoOutput
            });
            totalFrames += rqData.totalFrames;
        }

        var jobData = {
            name: jobName,
            plugin: "aftereffects",
            priority: priority,
            pool: "default",
            plugin_data: {
                mode: "render_queue",
                project_path: projectPath,
                rq_items: rqItems
            }
        };

        var result = httpRequest("POST", "/api/jobs", jobData);
        if (result && result.id) {
            var msg = "任务已提交!\n";
            msg += "Job ID: " + result.id + "\n";
            msg += "渲染项目: " + rqItems.length + "\n";
            msg += "总帧数: " + totalFrames;
            alert(msg);
        } else {
            alert("提交失败");
        }
    }

    /**
     * 模式2: 提交指定合成渲染
     */
    function submitCustomRenderMode(projectPath, jobName, priority, options) {
        if (!options.comp) {
            alert("请选择要渲染的合成");
            return;
        }

        if (!options.outputPath) {
            alert("请设置输出目录");
            return;
        }

        if (!options.outputPng && !options.outputProRes && !options.outputMp4) {
            alert("请至少选择一种输出格式");
            return;
        }

        // 构建输出格式列表
        var outputFormats = [];
        if (options.outputPng) outputFormats.push("png");
        if (options.outputProRes) outputFormats.push("prores4444");
        if (options.outputMp4) outputFormats.push("mp4");

        var jobData = {
            name: jobName,
            plugin: "aftereffects",
            priority: priority,
            pool: "default",
            plugin_data: {
                mode: "custom",
                project_path: projectPath,
                comp_name: options.comp.name,
                frame_start: options.frameStart,
                frame_end: options.frameEnd,
                output_path: options.outputPath,
                output_formats: outputFormats,
                width: options.comp.width,
                height: options.comp.height,
                frame_rate: options.comp.frameRate
            }
        };

        var result = httpRequest("POST", "/api/jobs", jobData);
        if (result && result.id) {
            alert("任务已提交!\nJob ID: " + result.id + "\n\n输出格式: " + outputFormats.join(", "));
        } else {
            alert("提交失败");
        }
    }

    // ============ 启动 ============
    buildUI(thisObj);

})(this);
