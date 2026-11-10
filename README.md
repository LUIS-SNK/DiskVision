# DiskVision

Aplicativo desktop em português para explorar o armazenamento local no Windows 10 ou 11. O aplicativo funciona offline e salva apenas preferências e histórico de operações no SQLite, na pasta local de dados do usuário.

## Executar a partir do código

Instale o Python 3.12 ou posterior para Windows x64. Em um PowerShell aberto na pasta do projeto, execute:

~~~powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
~~~

O download das dependências requer internet. Depois da instalação, o aplicativo funciona localmente.

## Fluxo de trabalho

1. Selecione uma unidade no painel geral e clique em **Explorar unidade**, ou escolha a letra na barra superior e clique em **Analisar unidade**.
2. No analisador, abra uma pasta com duplo clique na tabela ou com um clique no Treemap. Um clique em um arquivo no mapa seleciona sua linha. Ordene pelas colunas e use **Pasta acima** para voltar.
3. **Arquivos Grandes** filtra a unidade atual. **Duplicados** usa os resultados das unidades já analisadas e confirma os grupos por comparação byte a byte após o SHA-256 completo. Hard links para o mesmo arquivo e arquivos vazios são excluídos da busca de duplicados.
4. Em **Limpeza**, arquivos com mais de sete dias na pasta Temp local do usuário são identificados separadamente de candidatos por extensão. Revise os arquivos e decida individualmente o que deve ser enviado à Lixeira.
5. Selecione itens com Ctrl ou Shift, clique em **Mover para a Lixeira…** e revise a confirmação. Após o envio, o DiskVision remove da análise os itens enviados, atualiza os totais das pastas acima e consulta a capacidade das unidades. Use **Analisar unidade** para incorporar alterações feitas fora do DiskVision.

## Limites da análise

- A detecção cobre volumes locais com letra de unidade, incluindo mídias removíveis. Volumes montados apenas em diretórios, compartilhamentos de rede e discos sem volume montado ficam fora da lista.
- O Treemap apresenta os 100 maiores itens da pasta atual e agrega os demais. A tabela mostra os itens encontrados, inclusive os de tamanho zero.
- A soma das pastas usa o tamanho lógico dos arquivos encontrados. Hard links, compactação, arquivos esparsos, dados inacessíveis e metadados do sistema podem produzir diferenças em relação ao espaço ocupado reportado pelo Windows.
- A varredura ignora links e pontos de nova análise e continua diante de erros de acesso. O cancelamento mantém os resultados parciais encontrados até a operação de E/S atual terminar.
- Os itens são revalidados antes do envio à Lixeira. Uma pasta inteira é recusada se houver conteúdo desconhecido, protegido, inacessível ou em uso durante a validação. O sistema de arquivos pode sofrer alterações entre a validação e a operação do Windows. Revise novamente quando outra aplicação estiver alterando a pasta.
- Mover um arquivo para a Lixeira normalmente mantém o espaço ocupado até o esvaziamento. Unidades para as quais a Lixeira está indisponível podem recusar a operação.

## Gerar a distribuição

Para produzir o executável, instale as dependências de empacotamento no mesmo ambiente virtual:

~~~powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\build.ps1 -Python .\.venv\Scripts\python.exe
~~~

O aplicativo empacotado estará em **dist/DiskVision/DiskVision.exe**. Distribua a pasta inteira, pois ela contém as bibliotecas do Qt e o runtime Python.

Para produzir também o instalador, instale o Inno Setup 6 e execute:

~~~powershell
.\build.ps1 -Python .\.venv\Scripts\python.exe -Installer
~~~

Se necessário, use o parâmetro **-InnoSetup** com o caminho de **ISCC.exe**. O resultado será **dist/installer/DiskVision-Setup.exe**. A instalação é por usuário. O projeto de distribuição é voltado ao Windows x64.

## Organização

- **storage.py** detecta volumes, calcula a capacidade e varre diretórios.
- **duplicates.py** agrupa por tamanho, calcula hashes e compara conteúdo.
- **cleanup.py** classifica temporários e candidatos.
- **safe_files.py** valida seleções e integra a Lixeira do Windows.
- **ui.py**, **widgets.py** e **theme.py** implementam as telas, as tarefas em segundo plano e o Treemap.
- **preferences.py** mantém as preferências e o histórico local.
