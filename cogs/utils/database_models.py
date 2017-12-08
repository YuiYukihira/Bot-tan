from asyncqlio.orm.schema.column import Column
from asyncqlio.orm.schema.relationship import Relationship, ForeignKey
from asyncqlio.orm.schema.table import table_base
from asyncqlio.orm.schema.types import Text, BigInt

Table = table_base("Bot-tan")


class MGuild(Table):
    g_id = Column(BigInt, nullable=False)
    p_id = Column(BigInt, nullable=False, unique=True)

    g_playlists = Relationship(left=p_id, right="MPlaylist.p_id")
    p_info = Relationship(left=p_id, right="MPlaylistInfo.p_id")


class MPlaylist(Table):
    p_id = Column(BigInt, nullable=False, foreign_key=ForeignKey(MGuild.p_id), primary_key=True, unique=True)
    t_id = Column(BigInt, nullable=False, unique=True)

    p_tracks = Relationship(left=t_id, right="MTracks.t_id")


class MPlaylistInfo(Table):
    p_id = Column(BigInt, nullable=False, foreign_key=ForeignKey(MPlaylist.p_id), primary_key=True)
    p_name = Column(Text, nullable=False)
    p_creator = Column(Text, nullable=False)


class MTracks(Table):
    t_id = Column(BigInt, nullable=False, primary_key=True, foreign_key=ForeignKey(MPlaylist.t_id))
    t_name = Column(Text, nullable=False)
    t_uploader = Column(Text, nullable=False)
    t_url = Column(Text, nullable=False)
    t_file = Column(Text, nullable=False)
