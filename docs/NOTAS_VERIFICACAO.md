# Notas de verificação

Registro dos pontos que a seção 19 do `CENTRAL.md` manda confirmar contra a
realidade em vez de assumir de memória. Tudo aqui foi executado nesta máquina,
contra as versões efetivamente instaladas, em **2026-07-28**.

Quando uma verificação contradiz o `CENTRAL.md`, a divergência está anotada
aqui **e** emendada lá — este arquivo não é fonte de verdade, é a evidência.

| Componente | Versão verificada |
| --- | --- |
| Python | 3.12.13 |
| build123d | 0.11.1 |
| cadquery-ocp-novtk (OCCT) | 7.9.3.1.1 |
| lib3mf | 2.5.0 |
| VTK | 9.6.2 |
| PySide6 | 6.11.1 |
| trimesh | 4.12.2 |
| numpy | 2.5.1 |
| Bambu Studio | 02.07.01.62 |

---

## 1. A classe `Mesher` do build123d e o 3MF com múltiplos objetos

### Assinatura real

```python
Mesher.__init__(self, unit: Unit = Unit.MM)

Mesher.add_shape(
    self,
    shape: Shape | Iterable[Shape],
    linear_deflection: float = 0.001,
    angular_deflection: float = 0.1,
    mesh_type: MeshType = MeshType.MODEL,
    part_number: str | None = None,
    uuid_value: UUID | None = None,
)

Mesher.write(self, file_name: os.PathLike | str | bytes)
Mesher.read(self, file_name: os.PathLike | str | bytes) -> list[Shape]
```

Membros públicos: `add_code_to_metadata`, `add_meta_data`, `add_shape`,
`get_mesh_properties`, `get_meta_data`, `get_meta_data_by_key`,
`library_version`, `mesh_count`, `model_unit`, `read`, `triangle_counts`,
`vertex_counts`, `write`, `write_stream`.

### O que funciona

Múltiplos objetos num só arquivo funcionam com **uma chamada de `add_shape`
por corpo**. Duas chamadas produzem `mesh_count == 2` e dois build items.

### Armadilha 1 — `label` e `color` precisam estar no nível do `Solid`

`add_shape` começa assim:

```python
for input_shape in shape if isinstance(shape, Iterable) else [shape]:
    if isinstance(input_shape, Compound):
        shapes.extend(list(input_shape))
    else:
        shapes.append(input_shape)
```

`Part`, `Cylinder`, `Box` e afins **herdam de `Compound`**, então são explodidos
em seus sólidos filhos, e é dos filhos que `SetName(b3d_shape.label)` e
`_add_color(b3d_shape, ...)` leem. Marcar o invólucro não tem efeito nenhum.

Marcando no `Part` (errado), o XML sai sem nome e sem material:

```xml
<object id="1" partnumber="P1" type="model" p:UUID="8a630ea0-..."/>
<object id="3" partnumber="P2" type="model" p:UUID="9795e35d-..."/>
<!-- nenhum <base .../> -->
```

Marcando no `Solid` (certo):

```xml
<object id="1" name="base"  partnumber="base"  type="model" pid="2" pindex="0">
<object id="4" name="tampa" partnumber="tampa" type="model" pid="5" pindex="0">
<base name="Color: (0.5411765, 0.7058824, 0.972549, 1.0) near 'SKYBLUE2'" displaycolor="#8AB4F8FF"/>
<base name="Color: (0.9490196, 0.545098, 0.5098039, 1.0) near 'LIGHTCORAL'" displaycolor="#F28B82FF"/>
```

Nos dois casos `add_shape` também acrescenta um "components object" extra por
corpo, comentado no fonte como *"Not sure is this is required..."*.

### Armadilha 2 — `Mesher.read()` não restaura `label` nem `color`

Escrevendo dois corpos nomeados e coloridos e relendo:

```
lidos: 2
   label= '' color= None vol= 12561.2
   label= '' color= None vol= 6280.6
```

Portanto **teste de exportação inspeciona `3D/3dmodel.model` dentro do zip**,
nunca o round-trip por `read()`.

### Armadilha 3 — `linear_deflection` é relativo, não milímetros

`Mesher._mesh_shape` chama:

```python
BRepMesh_IncrementalMesh(
    theShape=ocp_mesh.wrapped,
    theLinDeflection=linear_deflection,
    isRelative=True,          # <-- fração do tamanho da aresta
    theAngDeflection=angular_deflection,
    isInParallel=True,
)
```

Com `isRelative=True` o desvio linear é **fração do tamanho da aresta**, não
uma medida absoluta. Num cilindro de raio 20 mm, três valores diferentes de
`linear_deflection` dão exatamente a mesma malha, porque 1,5 % de uma aresta de
40 mm é grosseiro demais para importar:

| `linear_deflection` | triângulos |
| --- | --- |
| 0.08 | 248 |
| 0.015 | 248 |
| 0.005 | 248 |
| 0.001 | 396 |
| 0.0002 | 888 |

Os valores da seção 6 do `CENTRAL.md` (0,08 mm no preview, 0,015 mm na
exportação) são **absolutos** e não podem ser passados aqui.

### Armadilha 4 — não dá para pré-tesselar e preservar a malha

Tentativa: tesselar o sólido em milímetros absolutos e depois chamar
`add_shape` com um desvio relativo frouxo, esperando que o OCCT reaproveite a
triangulação existente. Não funciona — `add_shape` faz `copy.deepcopy(shape)`
antes de malhar e **sempre remalha**:

```
tri após pré-malha absoluta 0,015 mm / 0,2 rad : 456
  Mesher(ld=0.01,  ad=0.2) -> escritos=248  REMALHOU
  Mesher(ld=0.05,  ad=0.5) -> escritos=100  REMALHOU
  Mesher(ld=0.001, ad=0.1) -> escritos=500  REMALHOU
```

### Consequência, e a decisão tomada

Usando o `Mesher`, o portão de qualidade da seção 8 validaria uma malha e o
arquivo gravaria **outra**. Isso esvazia a garantia do portão: aprova-se uma
peça e entrega-se outra.

**Decisão (aprovada em 2026-07-28):** a exportação escreve o 3MF com `lib3mf`
diretamente, a partir da malha exata que o portão aprovou. A dependência é a
mesma que o `CENTRAL.md` já cita — muda apenas quem a chama. Seção 9 emendada.

Protótipo validado:

```python
w = Wrapper()
model = w.CreateModel()
model.SetUnit(Lib3MF.ModelUnit.MilliMeter)
grupo = model.AddBaseMaterialGroup()

mo = model.AddMeshObject()
mo.SetName(corpo.nome)
mo.SetGeometry(
    [Lib3MF.Position((ctypes.c_float * 3)(*p)) for p in malha.vertices],
    [Lib3MF.Triangle((ctypes.c_uint * 3)(*f)) for f in malha.faces],
)
idx = grupo.AddMaterial(corpo.nome, w.RGBAToColor(r, g, b, 255))
mo.SetObjectLevelProperty(grupo.GetResourceID(), idx)
model.AddBuildItem(mo, w.GetIdentityTransform())

model.QueryWriter("3mf").WriteToFile(str(caminho))
```

Saída, mais limpa que a do `Mesher` — sem os objetos "components" espúrios:

```xml
<object id="2" name="base"  type="model" pid="1" pindex="0">
<object id="3" name="tampa" type="model" pid="1" pindex="1">
<base name="base"  displaycolor="#8AB4F8FF"/>
<base name="tampa" displaycolor="#F28B82FF"/>
unit="millimeter" | 2 build items | 912 triângulos
```

### Divergência secundária — `Corpo.filamento` não é gravável

A seção 9 dizia que corpos múltiplos vão para o 3MF *"preservando nomes e a
sugestão de filamento"*. Nomes ✔ e cor ✔, mas **filamento ✘**: índice de
filamento e atribuição de AMS são extensão proprietária do Bambu, gravada em
`Metadata/model_settings.config` dentro do 3MF, e a seção 10 já põe o formato
de projeto do Bambu explicitamente fora de escopo. O campo permanece no
contrato como metadado de exibição e para uso futuro. Seção 9 emendada.

---

## 2. `QVTKRenderWindowInteractor` na build de VTK instalada

O diretório `vtkmodules/qt/` **existe** nesta wheel, com
`QVTKRenderWindowInteractor.py` e `__init__.py`. O caminho de import correto é:

```python
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor
```

`vtkmodules.qt.PyQtImpl` vem como `None` e a detecção automática tenta, nesta
ordem: PySide6, PyQt6, PyQt5, PySide2, PyQt4, PySide. PySide6 é o primeiro e
tem suporte explícito no módulo. Ainda assim, `central/ui/viewport.py` **fixa**
o binding antes do import, para não depender de ordem de resolução:

```python
import vtkmodules.qt
vtkmodules.qt.PyQtImpl = "PySide6"
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor
```

`vtkmodules.qt.QVTKRWIBase` fica em `"QWidget"`, o padrão. Trocar para
`"QOpenGLWidget"` é aceito com PySide6, mas não há motivo para desviar do
padrão agora.

Teste de fumaça executado de verdade — `QApplication`, widget instanciado, cone
renderizado, `app.exec()` encerrando limpo:

```
OK  binding      : PySide6
OK  base widget  : QWidget
OK  actors       : 1
```

---

## 3. Flags de linha de comando do Bambu Studio

Instalação: `C:\Program Files\Bambu Studio\bambu-studio.exe`, versão
**02.07.01.62** (registro: `Bambu Studio`, `DisplayVersion 02.07.01.62`).
O executável tem 159 KB e é apenas o carregador de `BambuStudio.dll` (104 MB).
**Não existe** um `bambu-studio-console.exe`.

### Como a saída foi capturada, e por que isso importa

`bambu-studio.exe --help` com stdout redirecionado devolve **exit code 0 e zero
byte de saída**. O binário é do subsistema GUI do Windows: quando existe um
console no processo pai, ele o reata via `AttachConsole` e reabre `stdout` em
`CONOUT$`, escrevendo direto no buffer da tela e ignorando o redirecionamento.

A captura abaixo foi obtida rodando o executável num processo `pwsh` filho, com
console próprio, e lendo o buffer desse console com
`$Host.UI.RawUI.GetBufferContents()`.

Isso é uma restrição real para o nível avançado da seção 10 (fatiamento
headless), que fica fora da V1: ler a saída do modo CLI no Windows exige esse
mesmo contorno, ou o uso de `--pipe pipename`, que aparece na lista de flags.

### Resíduo no diretório de trabalho

O `bambu-studio.exe` grava um **`result.json` no diretório de trabalho
corrente**, mesmo quando invocado apenas com `--help`:

```json
{
    "error_string": "Success.",
    "export_time": 0,
    "layer_height": 0.0,
    "plate_index": 0,
    "prepare_time": 1,
    "return_code": 0,
    "sparse_infill_density": 0.0,
    "wall_loops": 0
}
```

Por isso `servicos/bambu.py` sempre invoca o executável com um `cwd`
controlado, e `result.json` está no `.gitignore` como rede de segurança.

### O que importa para a V1

O uso é `bambu-studio [ OPTIONS ] [ file.3mf/file.stl ... ]`. **Não existe flag
de "abrir arquivo"**: o nível intermediário da seção 10 passa o caminho do 3MF
como **argumento posicional**.

Para referência futura, o nível avançado usaria `--slice`, `--load-settings`,
`--outputdir` e `--export-slicedata`.

### Saída íntegra de `--help`

```
[2026-07-28 18:10:39.471280] [0x00002870] [trace]   Initializing StaticPrintConfigs
BambuStudio-02.07.01.62:
Usage: bambu-studio [ OPTIONS ] [ file.3mf/file.stl ... ]

OPTIONS:
 --allow-mix-temp option
                     Allow filaments with high/low temperature to be printed together
 --allow-multicolor-oneplate
                     If enabled, the arrange will allow multiple color on one plate
 --allow-newer-file option
                     Allow 3mf with newer version to be sliced
 --allow-rotations   If enabled, the arrange will allow rotations when place object
 --avoid-extrusion-cali-region
                     If enabled, the arrange will avoid extrusion calibrate region when place object
 --camera-view angle Camera view angle for exporting png: 0-Iso, 1-Top_Front, 2-Left, 3-Right,
                     10-Iso_1, 11-Iso_2, 12-Iso_3
 --clone-objects "1,3,1,10"
                     Clone objects in the load list
 --debug level       Sets debug logging level. 0:fatal, 1:error, 2:warning, 3:info, 4:debug, 5:trace
 --downward-check    if enabled, check whether current machine downward compatible with the machines
                     in the list
 --downward-settings "machine1.json;machine2.json;..."
                     the machine settings list need to do downward checking
 --enable-timelapse  If enabled, this slicing will be considered using timelapse
 --estimate-mode     When enabled, automatically fill filament presets and extruder state for machine
                     estimation after machine switch
 --load-assemble-list assemble_list.json
                     Load assemble object list from config file
 --load-custom-gcodes custom_gcode_toolchange.json
                     Load custom gcode from json
 --load-filament-ids "1,2,3,1"
                     Load filament ids for each object
 --load-filaments "filament1.json;filament2.json;..."
                     Load filament settings from the specified file list
 --load-settings "setting1.json;setting2.json"
                     Load process/machine settings from the specified file
 --makerlab-name name
                     MakerLab name to generate this 3mf
 --makerlab-version version
                     MakerLab version to generate this 3mf
 --metadata-name "name1;name2;..."
                     matadata name list added into 3mf
 --metadata-value "value1;value2;..."
                     matadata value list added into 3mf
 --outputdir dir     Output directory for the exported files.
 --skip-modified-gcodes option
                     Skip the modified gcodes in 3mf from Printer or filament Presets
 --skip-objects "3,5,10,77"
                     Skip some objects in this print
 --skip-useless-pick option
                     Skip generating useless pick/top images into 3mf
 --uptodate-filaments "filament1.json;filament2.json;..."
                     load uptodate filament settings from the specified file when using uptodate
 --uptodate-settings "setting1.json;setting2.json"
                     load uptodate process/machine settings from the specified file when using
                     uptodate
 --arrange option    Arrange options: 0-disable, 1-enable, others-auto
 --assemble          Arrange the supplied models in a plate and merge them in a single model in order
                     to perform actions once.
 --convert-unit      Convert the units of model
 --ensure-on-bed     Lift the object above the bed when it is partially below. Disabled by default
 --orient            Orient options: 0-disable, 1-enable, others-auto
 --repetitions count Repetition count of the whole model
 --rotate            Rotation angle around the Z axis in degrees.
 --rotate-x          Rotation angle around the X axis in degrees.
 --rotate-y          Rotation angle around the Y axis in degrees.
 --scale factor      Scale the model by a float factor
 --export-3mf filename.3mf
                     Export project as 3MF.
 --export-png option Export png of plate: 0-all plates, i-plate i, others-invalid
 --export-settings settings.json
                     Export settings to a file.
 --export-slicedata slicing_data_directory
                     Export slicing data to a folder.
 --export-stl        Export the objects as single STL.
 --export-stls       Export the objects as multiple stls to directory
 --help, -h          Show command help.
 --info              Output the model's information.
 --load-defaultfila option
                     Load first filament as default for those not loaded
 --load-slicedata slicing_data_directory
                     Load cached slicing data from directory
 --min-save option   export 3mf with minimum size.
 --mstpp time        max slicing time per plate in seconds.
 --mtcpp count       max triangle count per plate for slicing.
 --no-check          Do not run any validity checks, such as gcode path conflicts check.
 --normative-check option
                     Check the normative items.
 --pipe pipename     Send progress to pipe.
 --slice option      Slice the plates: 0-all plates, i-plate i, others-invalid
 --uptodate          Update the configs values of 3mf to latest.

Print settings priorites:
        1) setting values from the command line (highest priority)
        2) setting values loaded with --load_settings and --load_filaments
        3) setting values loaded from 3mf(lowest priority)
```

---

## 4. Tesselagem absoluta, soldagem de vértices e o portão de qualidade

A seção 19 diz que os desvios de tesselagem são ponto de partida, não medida.
Antes de calibrá-los no olho, era preciso confirmar que os valores da seção 6
significam alguma coisa quando aplicados **absolutamente**. Significam:
`BRepMesh_IncrementalMesh(..., isRelative=False, ...)`, num cilindro de raio 20:

| Nível | Desvio linear | Desvio angular | Triângulos | Estanque | Enrolamento | Erro de volume |
| --- | --- | --- | --- | --- | --- | --- |
| Preview | 0,08 mm | 0,5 rad | 196 | sim | consistente | 0,26 % |
| Exportação | 0,015 mm | 0,2 rad | 456 | sim | consistente | 0,05 % |

Duas descobertas de implementação:

1. **Vértices precisam ser soldados.** O OCCT emite a triangulação por face,
   com vértices duplicados nas costuras. Sem `trimesh.merge_vertices()` a malha
   **nunca** é estanque e o portão de qualidade reprovaria tudo. O `Mesher` do
   build123d resolve o mesmo problema arredondando à `TOLERANCE` e remapeando
   índices.
2. **`trimesh` 4.12.2 removeu `Trimesh.remove_degenerate_faces()`.** A seção 8
   fala em reparo com `trimesh.repair`; a API atual é
   `mesh.update_faces(mesh.nondegenerate_faces())` para descartar degeneradas,
   mais `trimesh.repair.fix_winding`, `fix_normals`, `fix_inversion` e
   `fill_holes`. Seção 8 emendada.

---

## 5. Fontes disponíveis para `Text`

`Arial` e `Segoe UI` existem nesta máquina e produzem contorno vetorial válido.

O ponto perigoso: **nome de fonte inexistente não levanta erro**. O gestor de
fontes do OCCT substitui em silêncio e apenas emite um aviso no stderr:

```
Font_FontMgr, warning: unable to find font 'DejaVu Sans' [regular];
'Arial' [...] is used instead
```

`Text(txt="Ana", font="DejaVu Sans")` devolveu geometria idêntica à do Arial.
Isso quebra a exigência de determinismo da seção 4: a mesma entrada produziria
geometria diferente em máquinas com conjuntos de fontes diferentes, corrompendo
o cache indexado por hash dos parâmetros sem nenhum sinal.

Por isso o helper `texto_solido` valida o nome da fonte contra as disponíveis e
falha explicitamente em vez de aceitar a substituição.
