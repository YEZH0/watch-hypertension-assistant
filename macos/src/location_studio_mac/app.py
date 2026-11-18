"""Native Qt desktop control panel. GPL-3.0-only."""
import sys

# Worker dispatch must precede GUI initialization, including in the frozen bundle.
if '--worker' in sys.argv:
    from .worker import run
    try:run()
    except Exception as error:
        import json
        print(json.dumps({'event':'error','type':type(error).__name__}),flush=True)
        raise SystemExit(1)
    raise SystemExit

import time
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, Signal, QPointF, QRectF
from PySide6.QtGui import QColor, QPainter, QPen, QPainterPath, QFont
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QFormLayout, QLabel, QLineEdit, QPushButton, QSpinBox, QFileDialog,
    QComboBox, QMessageBox, QPlainTextEdit, QSplitter, QFrame, QScrollArea,
    QGridLayout, QProgressBar, QToolButton)
from .engine import Engine, State, validate

CITIES = {'纽约 · New York': (40.7128,-74.0060), '伦敦 · London': (51.5074,-0.1278),
          '东京 · Tokyo': (35.6762,139.6503), '悉尼 · Sydney': (-33.8688,151.2093),
          '巴黎 · Paris': (48.8566,2.3522), '新加坡 · Singapore': (1.3521,103.8198)}


class BrandMark(QWidget):
    def __init__(self):
        super().__init__();self.setFixedSize(32,32)
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor('#22d3ee'),1.5));p.setBrush(QColor('#12313c'))
        p.drawRoundedRect(QRectF(1,1,30,30),8,8);p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(16,16),8,8);p.setBrush(QColor('#22d3ee'));p.drawEllipse(QPointF(16,16),3,3)


class Grid(QWidget):
    """Offline equirectangular world overview. No tile or search network requests."""
    selected = Signal(float,float)
    def __init__(self):
        super().__init__(); self.lat=40.7128; self.lon=-74.0060; self.zoom=1
        self.setMinimumSize(320,220)
        self.setAccessibleName('离线世界地图；点击选点，精确位置请填写 WGS-84 坐标')
        self.setCursor(Qt.CrossCursor)
        import json
        self.land=json.loads((Path(__file__).parent/'assets/world-land.json').read_text())['rings']

    def bounds(self):
        width,height=360/self.zoom,180/self.zoom
        cx=max(-180+width/2,min(180-width/2,self.lon))
        cy=max(-90+height/2,min(90-height/2,self.lat))
        return cx-width/2,cy+height/2,width,height

    def point(self,lon,lat):
        west,north,width,height=self.bounds()
        return QPointF((lon-west)/width*self.width(),(north-lat)/height*self.height())

    def change_zoom(self,factor):
        self.zoom=max(1,min(8,self.zoom*factor));self.update()

    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(),QColor('#090f17'))
        p.setPen(QPen(QColor('#162332'),1))
        for lon in range(-180,181,30):
            p.drawLine(self.point(lon,-90),self.point(lon,90))
        for lat in range(-90,91,30):
            p.drawLine(self.point(-180,lat),self.point(180,lat))
        p.setPen(QPen(QColor('#33485c'),.8));p.setBrush(QColor('#182a38'))
        for ring in self.land:
            path=QPainterPath();path.moveTo(self.point(*ring[0]))
            for point in ring[1:]: path.lineTo(self.point(*point))
            path.closeSubpath();p.drawPath(path)
        p.setPen(QColor('#94a9bb'))
        used=[]
        for name,(lat,lon) in CITIES.items():
            point=self.point(lon,lat)
            if 12<point.x()<self.width()-80 and 20<point.y()<self.height()-20:
                label=name.split(' · ')[0];rect=QRectF(point.x()+7,point.y()-21,p.fontMetrics().horizontalAdvance(label)+5,18)
                p.drawEllipse(point,2,2)
                if not any(rect.intersects(other) for other in used):
                    p.drawText(point+QPointF(7,-7),label);used.append(rect)
        target=self.point(self.lon,self.lat)
        p.setPen(QPen(QColor('#22d3ee'),1));p.setBrush(QColor(34,211,238,28));p.drawEllipse(target,21,21)
        p.setBrush(QColor('#22d3ee'));p.drawEllipse(target,6,6)
        p.drawLine(target+QPointF(-30,0),target+QPointF(-11,0))
        p.drawLine(target+QPointF(11,0),target+QPointF(30,0))
        p.drawLine(target+QPointF(0,-30),target+QPointF(0,-11))
        p.drawLine(target+QPointF(0,11),target+QPointF(0,30))
        p.setPen(QColor('#9bb0c6'));p.drawText(16,self.height()-16,'Natural Earth · 离线概览 / 非街道底图')

    def mousePressEvent(self,event):
        if self.isEnabled() and event.button()==Qt.LeftButton:
            west,north,width,height=self.bounds()
            self.selected.emit(north-event.position().y()/self.height()*height,
                               west+event.position().x()/self.width()*width)


class Window(QMainWindow):
    def __init__(self):
        super().__init__();self.setWindowTitle('iOS Location Studio · macOS');self.resize(1160,820);self.setMinimumSize(940,640)
        self.engine=Engine();self.state=State();self.mode=None;self.deadline=None
        self.closing=False;self.sending=False;self.needs_restore=False;self.session_duration=180;self.last_error=None
        self.engine.event.connect(self.on_event);self.engine.ended.connect(self.on_end)
        root=QWidget();self.setCentralWidget(root);shell=QHBoxLayout(root);shell.setContentsMargins(0,0,0,0);shell.setSpacing(0)
        sidebar=QScrollArea();sidebar.setObjectName('sidebar');sidebar.setWidgetResizable(True);sidebar.setFixedWidth(356)
        sidebar.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        left=QWidget();left.setObjectName('sideContent');sidebar.setWidget(left)
        form=QVBoxLayout(left);form.setContentsMargins(22,24,22,20);form.setSpacing(16)
        brand=QHBoxLayout();mark=BrandMark();brand.addWidget(mark)
        names=QVBoxLayout();title=QLabel('Location Studio');title.setObjectName('brandTitle');names.addWidget(title)
        subtitle=QLabel('iPhone 定位模拟 · macOS');subtitle.setObjectName('muted');names.addWidget(subtitle);brand.addLayout(names);brand.addStretch();form.addLayout(brand)
        self.route=QComboBox();self.route.addItem('DVT 开发者定位 · 推荐','dvt');self.route.addItem('iAP2 配件定位 · 实验','iap2');form.addWidget(self.route)
        self.prepare=QPushButton('准备开发者连接');self.prepare.clicked.connect(lambda:self.launch('dvt_prepare'));form.addWidget(self.prepare)
        device_box=QFrame();device_box.setObjectName('card');dv=QVBoxLayout(device_box);dv.setContentsMargins(14,12,14,12)
        dh=QHBoxLayout();dh.addWidget(QLabel('设备'));dh.addStretch();self.detect=QPushButton('检测 USB');self.detect.setObjectName('compact');self.detect.clicked.connect(lambda:self.launch('device'));dh.addWidget(self.detect);dv.addLayout(dh)
        self.device=QLabel('尚未连接 iPhone');self.device.setWordWrap(True);dv.addWidget(self.device)
        hint=QLabel('使用数据线连接，解锁并信任此电脑');hint.setObjectName('muted');hint.setWordWrap(True);dv.addWidget(hint);form.addWidget(device_box)
        session=QFrame();session.setObjectName('card');sv=QVBoxLayout(session);sv.setContentsMargins(14,12,14,14)
        sh=QHBoxLayout();sh.addWidget(QLabel('会话'));sh.addStretch();self.session_badge=QLabel('未启动');self.session_badge.setObjectName('pill');sh.addWidget(self.session_badge);sv.addLayout(sh)
        self.counter=QLabel('--:--');self.counter.setObjectName('counter');sv.addWidget(self.counter)
        self.countdown=QLabel('选择位置，开始一次限时测试');self.countdown.setObjectName('muted');self.countdown.setWordWrap(True);sv.addWidget(self.countdown)
        self.progress=QProgressBar();self.progress.setRange(0,1000);self.progress.setValue(0);self.progress.setTextVisible(False);self.progress.setFixedHeight(4);sv.addWidget(self.progress);form.addWidget(session)
        target_head=QHBoxLayout();target_head.addWidget(QLabel('目标坐标'));target_head.addStretch();copy=QPushButton('复制');copy.setObjectName('compact');copy.clicked.connect(self.copy_coordinates);target_head.addWidget(copy);form.addLayout(target_head)
        fields=QHBoxLayout();la=QVBoxLayout();lo=QVBoxLayout();la.addWidget(QLabel('纬度'));lo.addWidget(QLabel('经度'))
        self.lat=QLineEdit('40.712800');self.lon=QLineEdit('-74.006000');self.lat.setAccessibleName('WGS-84 纬度');self.lon.setAccessibleName('WGS-84 经度')
        la.addWidget(self.lat);lo.addWidget(self.lon);fields.addLayout(la);fields.addLayout(lo);form.addLayout(fields)
        self.city=QComboBox();self.city.setEditable(True);self.city.addItems(CITIES);self.city.setAccessibleName('离线城市搜索');self.city.setToolTip('搜索内置城市；其他位置请在地图选点或输入坐标')
        self.city.currentTextChanged.connect(self.city_changed);form.addWidget(self.city)
        times=QHBoxLayout();self.duration_buttons=[]
        for caption,seconds in [('1 分钟',60),('3 分钟',180)]:
            button=QPushButton(caption);button.setCheckable(True);button.setChecked(seconds==180);button.clicked.connect(lambda checked=False,s=seconds:self.duration.setValue(s));times.addWidget(button);self.duration_buttons.append((button,seconds))
        form.addLayout(times)
        dr=QHBoxLayout();dr.addWidget(QLabel('自定义时长'));self.duration=QSpinBox();self.duration.setRange(1,3600);self.duration.setValue(180);self.duration.setSuffix(' 秒');dr.addWidget(self.duration);form.addLayout(dr)
        self.duration.valueChanged.connect(self.duration_changed)
        self.start=QPushButton('开始模拟');self.start.setObjectName('primary');self.start.clicked.connect(lambda:self.launch('send'));form.addWidget(self.start)
        self.stop=QPushButton('停止发送 / 断开会话');self.stop.setObjectName('stop');self.stop.clicked.connect(self.engine.stop);form.addWidget(self.stop)
        form.addWidget(QLabel('快捷地点'));presets=QGridLayout();self.quick_buttons=[]
        for i,(name,coords) in enumerate(CITIES.items()):
            button=QPushButton(name.split(' · ')[0]);button.clicked.connect(lambda checked=False,n=name:self.city.setCurrentText(n));presets.addWidget(button,i//2,i%2);self.quick_buttons.append(button)
        form.addLayout(presets)
        self.cert=QLineEdit();self.key=QLineEdit();self.auth_widgets=[]
        default=Path.home()/'Library/Application Support/accessory-location/identity'
        auth=QWidget();av=QVBoxLayout(auth);av.setContentsMargins(0,4,0,4);av.setSpacing(8)
        for field,name,caption in ((self.cert,'certificate.p7b','证书'),(self.key,'identity.pk8','私钥')):
            if (default/name).is_file():field.setText(str(default/name))
            field.setPlaceholderText('选择本机'+caption);field.setReadOnly(True);field.setToolTip(field.text())
            row=QHBoxLayout();row.addWidget(field);button=QPushButton('选择'+caption);button.setObjectName('compact');button.clicked.connect(lambda checked=False,f=field:self.pick(f));row.addWidget(button);av.addLayout(row);self.auth_widgets.append(button)
        self.probe=QPushButton('检查通信与认证 · 20 秒');self.probe.clicked.connect(lambda:self.launch('probe'));av.addWidget(self.probe)
        advanced=QToolButton();advanced.setText('认证设置与通信检查');advanced.setCheckable(True);advanced.setArrowType(Qt.RightArrow);advanced.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        advanced.toggled.connect(lambda checked:(auth.setVisible(checked),advanced.setArrowType(Qt.DownArrow if checked else Qt.RightArrow)))
        self.advanced=advanced;self.auth=auth
        form.addWidget(advanced);form.addWidget(auth);auth.hide()
        self.warning=warning=QLabel('iAP2 实验方案\n认证或 ACK 不代表位置已改变。请在手机验证，并在结束后确认恢复。');warning.setObjectName('warning');warning.setWordWrap(True);form.addWidget(warning)
        author=QLabel('欧耶哥爱数码\n抖音 / 小红书同名 · 仅用于合法定位测试');author.setObjectName('muted');author.setWordWrap(True);form.addWidget(author);form.addStretch()
        side_container=QWidget();side_container.setFixedWidth(356);side_layout=QVBoxLayout(side_container)
        side_layout.setContentsMargins(0,0,0,0);side_layout.setSpacing(0);side_layout.addWidget(sidebar,1)
        actions=QWidget();actions.setObjectName('actionBar');action_layout=QVBoxLayout(actions)
        action_layout.setContentsMargins(22,12,22,16);action_layout.setSpacing(8)
        form.removeWidget(self.start);form.removeWidget(self.stop)
        action_layout.addWidget(self.start);action_layout.addWidget(self.stop);side_layout.addWidget(actions)
        shell.addWidget(side_container)
        workspace=QWidget();right=QVBoxLayout(workspace);right.setContentsMargins(24,24,24,20);right.setSpacing(14)
        top=QHBoxLayout();heading=QLabel('目标位置');heading.setObjectName('heading');top.addWidget(heading);top.addStretch();badge=QLabel('离线世界地图 · WGS-84');badge.setObjectName('pill');top.addWidget(badge);right.addLayout(top)
        self.target_label=QLabel('纽约 · New York   /   40.712800, -74.006000');self.target_label.setObjectName('muted');self.target_label.setWordWrap(True);right.addWidget(self.target_label)
        self.notice=notice=QLabel('实验性 iAP2 · 认证 / ACK 不代表手机采用位置');notice.setObjectName('notice');notice.setWordWrap(True);right.addWidget(notice)
        toolbar=QHBoxLayout();tip=QLabel('点击选点，或输入精确坐标');tip.setObjectName('muted');toolbar.addWidget(tip);toolbar.addStretch()
        self.grid=Grid();self.grid.selected.connect(self.set_coordinates)
        for text,callback in [('−',lambda:self.grid.change_zoom(.5)),('+',lambda:self.grid.change_zoom(2)),('全球',self.reset_map)]:
            button=QPushButton(text);button.setObjectName('compact');button.setAccessibleName({'−':'缩小地图','+':'放大地图','全球':'显示全球'}[text]);button.clicked.connect(callback);toolbar.addWidget(button)
        right.addLayout(toolbar);right.addWidget(self.grid,1)
        self.lat.editingFinished.connect(self.update_target);self.lon.editingFinished.connect(self.update_target)
        state_head=QLabel('连接与验证');state_head.setObjectName('sectionTitle');right.addWidget(state_head)
        self.status=QLabel();self.status.setWordWrap(True);self.status.setObjectName('status');right.addWidget(self.status)
        verification=QHBoxLayout();self.map_button=QPushButton('确认手机位置已改变');self.map_button.clicked.connect(self.confirm_map);verification.addWidget(self.map_button)
        self.restore=QPushButton('确认已恢复真实定位');self.restore.clicked.connect(self.confirm_restore);verification.addWidget(self.restore);right.addLayout(verification)
        log_toggle=QToolButton();log_toggle.setText('查看会话日志');log_toggle.setCheckable(True);log_toggle.setArrowType(Qt.RightArrow);log_toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.log=QPlainTextEdit();self.log.setReadOnly(True);self.log.setMaximumBlockCount(120);self.log.setFixedHeight(110)
        log_toggle.toggled.connect(lambda checked:(self.log.setVisible(checked),self.grid.setMinimumHeight(110 if checked else 220),log_toggle.setArrowType(Qt.DownArrow if checked else Qt.RightArrow)))
        right.addWidget(log_toggle);right.addWidget(self.log);self.log.hide()
        self.footer=footer=QLabel('USB iAP2 · 本机运行   |   上游 accessory-location · GPL-3.0-only');footer.setObjectName('muted');footer.setWordWrap(True);right.addWidget(footer)
        shell.addWidget(workspace,1)
        self.route.currentIndexChanged.connect(self.route_changed);self.route_changed()
        self.timer=QTimer(self);self.timer.timeout.connect(self.tick);self.timer.start(250);self.refresh()

    def route_changed(self):
        dvt=self.route.currentData()=='dvt'
        self.warning.setText('DVT 开发者定位\n请在手机确认位置变化，停止后确认真实定位恢复。' if dvt else 'iAP2 实验方案\n认证或 ACK 不代表位置已改变。请在手机验证，并在结束后确认恢复。')
        self.footer.setText(('USB DVT' if dvt else 'USB iAP2')+' · 本机运行   |   GPL-3.0-only')
        self.prepare.setVisible(dvt);self.advanced.setVisible(not dvt)
        self.auth.setVisible(not dvt and self.advanced.isChecked())
        self.duration.setMaximum(180 if dvt else 3600)
        self.notice.setText('DVT 开发者定位 · 请求已发送仍需在手机验证' if dvt else '实验性 iAP2 · 认证 / ACK 不代表手机采用位置')
        self.refresh()

    def copy_coordinates(self):
        try:
            lat,lon,_=validate(self.lat.text(),self.lon.text(),self.duration.value())
            QApplication.clipboard().setText(f'{lat:.6f}, {lon:.6f}')
            self.target_label.setText(f'坐标已复制   /   {lat:.6f}, {lon:.6f}')
        except ValueError: self.target_label.setText('坐标无效，请填写正确的 WGS-84 经纬度')

    def duration_changed(self,value):
        for button,seconds in self.duration_buttons:button.setChecked(value==seconds)

    def reset_map(self):
        self.grid.zoom=1;self.grid.update()

    def update_target(self):
        try:
            lat,lon,_=validate(self.lat.text(),self.lon.text(),self.duration.value())
            self.grid.lat=lat;self.grid.lon=lon;self.grid.update()
            place=next((name for name,coords in CITIES.items() if abs(coords[0]-lat)<.00001 and abs(coords[1]-lon)<.00001),'自定义位置')
            self.target_label.setText(f'{place}   /   {lat:.6f}, {lon:.6f}')
        except ValueError:self.target_label.setText('坐标无效：纬度 −90～90，经度 −180～180')

    def pick(self,field):
        if self.engine.running: return
        path,_=QFileDialog.getOpenFileName(self,'选择本地 MFi 身份文件')
        if path: field.setText(path);field.setToolTip(path)

    def city_changed(self,text):
        if text in CITIES: self.set_coordinates(*CITIES[text])

    def set_coordinates(self,lat,lon):
        self.lat.setText(f'{lat:.6f}'); self.lon.setText(f'{lon:.6f}')
        self.update_target()

    def launch(self,mode):
        try:
            if self.needs_restore and mode=='send':
                raise ValueError('请先完成上次会话的真实定位恢复确认')
            route=self.route.currentData()
            if mode=='dvt_prepare':
                if QMessageBox.question(self,'准备开发者连接','将使用 Apple 官方 devicectl 准备开发者镜像。首次可能向 Apple 发送 ECID、芯片/主板编号、nonce 和镜像摘要申请票据，不发送坐标或 MFi 私钥。是否同意？')!=QMessageBox.Yes:return
            lat,lon,duration=validate(self.lat.text(),self.lon.text(),self.duration.value()) if mode=='send' else (0,0,20)
            if mode=='send':
                answer=QMessageBox.question(self,'确认定位测试',f'向 iPhone 发送 WGS-84 坐标 {lat:.6f}, {lon:.6f}，持续 {duration} 秒？\n请在手机苹果地图点击当前位置。')
                if answer!=QMessageBox.Yes: return
            if mode in ('probe','send') and route=='iap2':
                from .worker import resources
                import importlib.util
                spec=importlib.util.spec_from_file_location('mfi_validation',resources()/'tools/local_mfi_v3_helper.py')
                module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
                module.validate_identity(Path(self.cert.text()).read_bytes(),Path(self.key.text()).read_bytes())
            self.last_error=None
            self.state=State(); self.mode=mode
            self.engine.start(mode,self.cert.text(),self.key.text(),lat,lon,duration,route=route)
            if mode=='dvt_prepare':duration=75
            self.session_duration=duration
            self.deadline=time.monotonic()+duration; self.sending=mode=='send'
            if self.sending: self.needs_restore=True
            self.log.clear(); self.refresh()
        except Exception as e:
            # Do not display file data or identifiers in arbitrary exception messages.
            text=str(e) if isinstance(e,ValueError) else '启动失败，请检查设备连接与当前路线的准备状态。'
            QMessageBox.warning(self,'无法启动',text)

    def on_event(self,event):
        self.state.consume(event)
        name=event.get('event','unknown')
        labels={'device_connected':'USB 已连接','identification_accepted':'身份识别已接受',
                'authentication_succeeded':'认证成功','location_requested':'手机请求定位订阅',
                'location_stopped':'手机停止订阅','location_link_acknowledged':'链路 ACK（不代表位置采纳）',
                'error':'协议错误，请检查手机连接、身份有效性与兼容性',
                'process_error':'进程启动失败，请检查沙箱和应用完整性',
                'interrupted':'会话已停止','finished':'限时会话已结束','process_exit':'工作进程已退出'}
        labels.update({'dvt_tunnel_connected':'DVT 隧道已建立','dvt_probe_succeeded':'开发者通道检查成功（未发送坐标）','dvt_set_sent':'DVT 坐标请求已发送，请在手机验证','dvt_clear_sent':'已发送清除请求，请确认真实位置','dvt_session_closed':'DVT 会话已关闭','dvt_clear_error':'清除请求失败，请断开 USB 并检查真实位置','developer_image_preparation':'开发者镜像准备已返回，请检查通道'})
        if name=='error':
            labels['error']={'DVTImageRequired':'请先点击“准备开发者连接”','DeveloperModeRequired':'请在 iPhone 开启开发者模式后重试','RequireExactlyOneUSBDevice':'请仅连接一台 iPhone，解锁并信任','XcodeRequired':'开发者镜像准备需要安装完整 Xcode'}.get(event.get('type'),'定位通道失败，请停止并检查设备连接和准备状态')
        if name=='developer_image_preparation' and event.get('exit_code')!=0:labels[name]='开发者镜像准备失败，请检查 Xcode、手机解锁与授权'
        if name=='dvt_tunnel_connected':self.device.setText('iPhone 已通过 USB 开发者通道连接')
        if name=='error':self.last_error=labels['error']
        if name=='process_exit' and event.get('code',0)!=0:
            self.last_error=self.last_error or '工作进程异常退出，请检查应用完整性与准备状态'
            labels[name]=self.last_error
        if name=='device_ready': self.device.setText(f'USB 已配对 · {event["model"]} · iOS {event["ios"]}')
        if name=='device_count': self.device.setText('请仅连接一台 USB iPhone，再解锁并信任后重试。')
        if name=='device_error': self.device.setText('连接失败：检查 USB、解锁与信任授权。')
        if name in labels: self.log.appendPlainText(labels[name])
        self.refresh()

    def refresh(self):
        busy=self.engine.running
        for widget in (self.detect,self.probe,self.prepare,self.route,self.start,self.city,self.lat,self.lon,self.duration,self.grid,*self.quick_buttons,*self.auth_widgets,*(b for b,_ in self.duration_buttons)): widget.setEnabled(not busy)
        self.stop.setEnabled(busy)
        self.session_badge.setText("发送中" if busy and self.sending else "检查中" if busy else "待确认恢复" if self.needs_restore else "失败" if self.last_error else "未启动")
        self.map_button.setEnabled(busy and self.sending and (self.state.acks>0 or self.state.dvt_set) and not self.state.map_verified)
        self.restore.setEnabled(not busy and self.needs_restore)
        if self.route.currentData()=='dvt':
            self.status.setText(f'DVT 通道：{"已连接" if self.state.dvt_connected else "未验证"}   ·   坐标请求：{"已发送" if self.state.dvt_set else "未发送"}\n手机位置：{"用户已确认改变" if self.state.map_verified else "尚未人工验证"}   ·   恢复：{"用户已确认" if self.state.restored else "未确认"}')
        else:
            self.status.setText(f'身份识别：{"已接受" if self.state.identified else "未验证"}   ·   认证：{"成功" if self.state.authenticated else "未验证"}\n订阅：{"活跃" if self.state.subscribed else "未订阅 / 已停止"}   ·   ACK：{self.state.acks}\n手机位置：{"用户已确认改变" if self.state.map_verified else "尚未人工验证"}   ·   恢复：{"用户已确认" if self.state.restored else "未确认"}')

    def tick(self):
        if self.engine.running and self.deadline:
            remaining=max(0,int(self.deadline-time.monotonic()))
            self.counter.setText(f'{remaining//60:02d}:{remaining%60:02d}')
            self.countdown.setText('握手及连接最多额外 30 秒' if not remaining else '剩余时间 · 请在手机验证位置')
            self.progress.setValue(int(1000*min(1,max(0,1-remaining/max(1,self.session_duration)))))
        else:
            self.counter.setText('--:--');self.progress.setValue(0)
            self.countdown.setText(('失败：'+self.last_error) if self.last_error else '已停止，请确认真实定位恢复' if self.needs_restore else '未运行 · 无后台定位任务')
        self.refresh()

    def on_end(self):
        self.deadline=None; self.refresh()
        if self.needs_restore:
            self.log.appendPlainText('请断开 USB，在苹果地图确认真实位置。若仍保留模拟位置，关闭定位服务约 10 秒再开启。')
        if self.closing: self.close()

    def confirm_map(self):
        self.state.map_verified=True; self.refresh()

    def confirm_restore(self):
        if QMessageBox.question(self,'真实定位验证','已断开 USB，并在苹果地图看到真实位置了吗？')==QMessageBox.Yes:
            self.state.restored=True; self.needs_restore=False; self.refresh()

    def closeEvent(self,event):
        if self.engine.running:
            self.closing=True; self.engine.stop(); event.ignore()
        else:
            if self.needs_restore:
                QMessageBox.information(self,'恢复提醒','发送已停止。请断开 USB 并在手机确认真实定位恢复；本应用未验证恢复结果。')
            event.accept()


STYLE = '\nQWidget {background:#070a0f;color:#e8eef7;font-size:13px;}\nQWidget#sideContent,QWidget#actionBar {background:#0d131b;} QLabel {background:transparent;} QLabel#notice {color:#f7cc70;font-size:11px;} QScrollArea#sidebar {border:0;border-right:1px solid #1e2b3a;}\nQFrame#card {background:#111922;border:1px solid #26384a;border-radius:10px;}\nQFrame#card QLabel {background:transparent;}\nQLabel#brandTitle {font-size:20px;font-weight:600;} QLabel#brandMark {font-size:28px;color:#22d3ee;}\nQLabel#heading {font-size:22px;font-weight:600;} QLabel#counter {font-size:38px;font-weight:600;}\nQLabel#muted {color:#a0b1c4;font-size:11px;} QLabel#pill {color:#a9bfd0;background:#16232e;border-radius:5px;padding:4px 8px;font-size:11px;}\nQLabel#warning {color:#f7cc70;background:#211d14;padding:12px;border-radius:7px;font-size:12px;}\nQLabel#sectionTitle {font-weight:600;} QLabel#status {color:#b8cadb;line-height:1.5;}\nQLineEdit,QComboBox,QSpinBox,QPlainTextEdit {background:#111922;border:1px solid #35485e;padding:8px;border-radius:6px;selection-background-color:#22d3ee;selection-color:#070a0f;}\nQLineEdit:focus,QComboBox:focus,QSpinBox:focus {border:1px solid #22d3ee;}\nQComboBox QAbstractItemView {background:#111922;selection-background-color:#203a4c;}\nQPushButton {background:#16202b;border:1px solid #35485e;border-radius:6px;padding:9px 10px;}\nQPushButton:hover {background:#203143;border-color:#69849b;} QPushButton:focus {border:1px solid #22d3ee;}\nQPushButton:checked {color:#22d3ee;background:#12313c;border-color:#22d3ee;}\nQPushButton#compact {padding:5px 9px;font-size:11px;}\nQPushButton#primary {background:#22d3ee;color:#06131b;font-weight:600;padding:12px;}\nQPushButton#primary:hover {background:#67e8f9;}\nQPushButton#stop {color:#ffb4b4;} QPushButton:disabled,QPushButton#primary:disabled,QPushButton#stop:disabled {background:#101923;color:#8294a7;border-color:#263646;}\nQToolButton {border:0;background:transparent;color:#a7bfd1;padding:6px 0;text-align:left;}\nQToolButton:hover {color:#22d3ee;} QToolButton:focus {border:1px solid #22d3ee;}\nQProgressBar {border:0;background:#243444;border-radius:2px;} QProgressBar::chunk {background:#22d3ee;border-radius:2px;}\nQScrollBar:vertical {background:#0d131b;width:7px;} QScrollBar::handle:vertical {background:#34495b;min-height:32px;border-radius:3px;}\nQScrollBar::add-line:vertical,QScrollBar::sub-line:vertical {height:0;}\n'

def main():
    app=QApplication(sys.argv); app.setApplicationName('iOS Location Studio')
    app.setFont(QFont('PingFang SC',13))
    app.setStyleSheet(STYLE)
    window=Window(); window.show(); return app.exec()

if __name__=='__main__': raise SystemExit(main())
