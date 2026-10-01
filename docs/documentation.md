# 构建文档网站

文档源文件位于 `docs/`，导航和站点设置位于 `mkdocs.yml`。生成的 HTML 位于 `site/`，该目录不应提交到 Git。

## 本地预览

在项目虚拟环境中安装文档依赖：

```powershell
python -m pip install --index-url https://pypi.org/simple/ -r requirements-docs.txt
python -m mkdocs serve
```

访问 `http://127.0.0.1:8000/`。修改 Markdown 后，开发服务器会自动重新构建页面。

## 构建静态 HTML

```powershell
python -m mkdocs build --strict
```

`--strict` 会将导航或内部链接警告视为构建失败。将 `site/` 的内容上传到任意静态网站服务即可发布。

## GitHub Pages

仓库提供 `.github/workflows/docs.yml`：

1. 打开仓库的 **Settings → Pages**。
2. 将 **Build and deployment → Source** 设置为 **GitHub Actions**。
3. 推送到 `master` 或 `main`，或手动运行 `Docs` workflow。
4. 在 workflow 的 deployment URL 或仓库 Pages 设置中打开网站。

从模板创建新项目后，更新 `mkdocs.yml` 中的 `site_name`、`site_description`、`repo_name`、`repo_url` 和 `edit_uri`。

## 文档结构

```text
mkdocs.yml                  MkDocs 配置和导航
requirements-docs.txt      文档构建依赖
pyproject.toml             所有直接依赖和 profile 的唯一配置源
docs/                       中文文档
docs/en/                    英文文档
docs/images/                两种语言共用的图片
.github/workflows/docs.yml  GitHub Pages 构建与部署
site/                       生成的静态 HTML（已忽略）
```

新增页面后，将页面加入 `mkdocs.yml` 的 `nav`，并执行严格构建检查。
