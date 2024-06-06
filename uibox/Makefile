build:
	@go work use .
	@GOOS=linux GOARCH=arm64 go build -o uibox main.go


# Define color codes
GREEN := \033[32m
YELLOW := \033[33m
RESET := \033[0m

ADB_ARGS := "-d"

define echo
    @echo ">>> $(GREEN)$(1)$(RESET)"
endef


test: build
	@adb $(ADB_ARGS) shell getprop ro.product.cpu.abilist
	@$(call echo,Pushing uibox to /data/local/tmp/uibox)
	@adb $(ADB_ARGS) push uibox /data/local/tmp/uibox
	@adb $(ADB_ARGS) shell chmod 777 /data/local/tmp/uibox
	@$(call echo,Running uibox)
	@adb $(ADB_ARGS) shell /data/local/tmp/uibox -h