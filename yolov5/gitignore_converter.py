# .gitignore ファイルのパスを指定します。
gitignore_path = ".gitignore"

# 新しい行を保存するリストを初期化します。
new_lines = []

# .gitignore ファイルを読み込み、各行の前に "yolov5/" を追加します。
with open(gitignore_path, "r") as file:
    lines = file.readlines()
    for line in lines:
        # 空行またはコメント行の場合、変更せずにそのままリストに追加します。
        if line.startswith("#") or line.strip() == "":
            new_lines.append(line)
        else:
            # それ以外の行は "yolov5/" を前に追加します。
            new_lines.append(f"yolov5/{line}")

# 新しい内容で .gitignore ファイルを上書きします。
with open(gitignore_path, "w") as file:
    file.writelines(new_lines)

