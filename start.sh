#!/bin/bash
#
# CSV Sync Server 启动脚本
# 兼容 macOS / Linux / Windows (Git Bash/WSL)
#

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

print_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
print_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# 检测操作系统
detect_os() {
    case "$(uname -s)" in
        Darwin*)  OS="mac" ;;
        Linux*)   OS="linux" ;;
        MINGW*|MSYS*|CYGWIN*) OS="windows" ;;
        *)        OS="unknown" ;;
    esac
    print_info "检测到操作系统: $OS"
}

# 检查命令是否存在
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# 安装 Docker
install_docker() {
    print_warn "Docker 未安装，尝试安装..."
    
    case "$OS" in
        mac)
            if command_exists brew; then
                print_info "使用 Homebrew 安装 Docker..."
                brew install --cask docker
                print_warn "请手动启动 Docker Desktop 应用程序，然后重新运行此脚本"
                exit 1
            else
                print_error "请先安装 Homebrew 或手动安装 Docker Desktop"
                print_info "下载地址: https://www.docker.com/products/docker-desktop"
                exit 1
            fi
            ;;
        linux)
            if command_exists apt-get; then
                print_info "使用 apt 安装 Docker..."
                sudo apt-get update
                sudo apt-get install -y docker.io docker-compose
                sudo systemctl start docker
                sudo systemctl enable docker
                sudo usermod -aG docker "$USER"
                print_warn "请重新登录以使 docker 组权限生效"
            elif command_exists yum; then
                print_info "使用 yum 安装 Docker..."
                sudo yum install -y docker docker-compose
                sudo systemctl start docker
                sudo systemctl enable docker
                sudo usermod -aG docker "$USER"
            else
                print_error "无法自动安装 Docker，请手动安装"
                exit 1
            fi
            ;;
        windows)
            print_error "Windows 请手动安装 Docker Desktop"
            print_info "下载地址: https://www.docker.com/products/docker-desktop"
            exit 1
            ;;
        *)
            print_error "不支持的操作系统"
            exit 1
            ;;
    esac
}

# 检查 Docker 是否运行
check_docker_running() {
    if ! docker info >/dev/null 2>&1; then
        print_warn "Docker 未运行"
        
        case "$OS" in
            mac)
                print_info "尝试启动 Docker Desktop..."
                open -a Docker
                print_info "等待 Docker 启动 (最多60秒)..."
                for i in {1..60}; do
                    if docker info >/dev/null 2>&1; then
                        print_info "Docker 已启动"
                        return 0
                    fi
                    sleep 1
                done
                print_error "Docker 启动超时，请手动启动 Docker Desktop"
                exit 1
                ;;
            linux)
                print_info "尝试启动 Docker 服务..."
                sudo systemctl start docker
                sleep 3
                ;;
            windows)
                print_error "请手动启动 Docker Desktop"
                exit 1
                ;;
        esac
    fi
}

# 安装 curl
install_curl() {
    print_warn "curl 未安装，尝试安装..."
    
    case "$OS" in
        mac)
            brew install curl
            ;;
        linux)
            if command_exists apt-get; then
                sudo apt-get install -y curl
            elif command_exists yum; then
                sudo yum install -y curl
            fi
            ;;
        windows)
            print_error "请手动安装 curl"
            exit 1
            ;;
    esac
}

# 等待服务就绪
wait_for_service() {
    print_info "等待服务启动..."
    for i in {1..30}; do
        if curl -s http://localhost:8000/api/v1/health >/dev/null 2>&1; then
            print_info "服务已就绪"
            return 0
        fi
        sleep 1
    done
    print_error "服务启动超时"
    exit 1
}

# 主流程
main() {
    print_info "=== CSV Sync Server 启动脚本 ==="
    
    # 检测系统
    detect_os
    
    # 检查并安装 Docker
    if ! command_exists docker; then
        install_docker
    fi
    print_info "Docker 已安装 ✓"
    
    # 检查 Docker 是否运行
    check_docker_running
    print_info "Docker 运行中 ✓"
    
    # 检查并安装 curl
    if ! command_exists curl; then
        install_curl
    fi
    print_info "curl 已安装 ✓"
    
    # 检测 docker compose 命令
    if command_exists docker-compose; then
        COMPOSE_CMD="docker-compose"
    else
        COMPOSE_CMD="docker compose"
    fi
    print_info "使用命令: $COMPOSE_CMD"
    
    # 启动服务
    print_info "启动 Docker 容器..."
    $COMPOSE_CMD up --build -d
    
    # 等待服务就绪
    wait_for_service
    
    # 测试上传
    print_info "=== 测试文件上传 ==="
    
    TEST_FILE="backend/sync-server/test_data.csv"
    if [ -f "$TEST_FILE" ]; then
        print_info "上传测试文件: $TEST_FILE"
        echo ""
        curl -X POST http://localhost:8000/api/v1/upload \
            -F "file=@$TEST_FILE" \
            -w "\n"
        echo ""
    else
        print_warn "测试文件不存在: $TEST_FILE"
    fi
    
    print_info "=== 完成 ==="
    print_info "API 文档: http://localhost:8000/docs"
    print_info "健康检查: http://localhost:8000/api/v1/health"
    print_info "停止服务: $COMPOSE_CMD down"
}

main "$@"
